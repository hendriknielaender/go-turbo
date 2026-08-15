# Allocation

Treat heap allocation as work, not as a defect by itself. An allocation pays
allocator cost immediately; reachable pointer-bearing objects add mark work;
dead objects still need reclamation. Optimize allocation only on a measured
hot path, and report `allocs/op` and `B/op` with time.

## Contents

- [Find the allocation first](#find-the-allocation-first)
- [Preallocate known work](#preallocate-known-work)
- [Let slices and maps grow when size is uncertain](#let-slices-and-maps-grow-when-size-is-uncertain)
- [Keep text in one representation](#keep-text-in-one-representation)
- [Build strings once](#build-strings-once)
- [Distinguish interface conversion from heap allocation](#distinguish-interface-conversion-from-heap-allocation)
- [Pool only proven temporary churn](#pool-only-proven-temporary-churn)
- [Lay out dense structs deliberately](#lay-out-dense-structs-deliberately)
- [Separate contended fields only after proving false sharing](#separate-contended-fields-only-after-proving-false-sharing)
- [Make aliasing an ownership decision](#make-aliasing-an-ownership-decision)
- [Break accidental backing-store retention](#break-accidental-backing-store-retention)
- [Version compatibility](#version-compatibility)

## Find the allocation first

Use a benchmark to count per-operation churn and a profile to locate it:

```sh
go test ./path/to/pkg -run='^$' -bench='BenchmarkHot' -benchmem -count=10
go tool pprof -sample_index=alloc_objects http://localhost:6060/debug/pprof/allocs
go tool pprof -sample_index=alloc_space http://localhost:6060/debug/pprof/allocs
```

Object count finds allocator and GC churn; allocated bytes find large copies
and buffers. The allocation profile is sampled, so confirm a proposed fix in
the benchmark. Do not add pooling, aliasing, or `unsafe` from escape output
alone.

**Use when:** allocation appears in a representative profile or benchmark.
**Backfires when:** the benchmark omits the retaining consumer, concurrency,
or realistic input distribution and therefore rewards a lifetime bug.

## Preallocate known work

Give slices capacity when the expected result count is known or tightly
bounded:

```go
func convertAll(rows []Row) []Result {
	results := make([]Result, 0, len(rows))
	for _, row := range rows {
		results = append(results, convert(row))
	}
	return results
}
```

Allocate the final length and assign by index when every output slot is
written exactly once:

```go
func convertAll(rows []Row) []Result {
	results := make([]Result, len(rows))
	for i, row := range rows {
		results[i] = convert(row)
	}
	return results
}
```

Use a map hint for a credible entry count:

```go
index := make(map[string]int, len(keys))
```

The map argument is an initial-size hint, not a capacity contract. Its effect
depends on key/value sizes and the current map implementation.

**Use when:** the bound is cheap to obtain and close to typical occupancy.
**Backfires when:** the bound is an adversarial or rare maximum, the result is
usually filtered down, or `make([]T, n)` is followed by `append` and silently
leaves `n` zero values at the front.

## Let slices and maps grow when size is uncertain

`append` uses an implementation-defined growth policy coordinated with
allocator size classes. Growth allocates a new backing array and copies the
old elements only when capacity is exhausted. Do not encode current growth
thresholds into application logic.

For untrusted or highly variable input, start small or cap the initial hint:

```go
const initialLimit = 1024

hint := len(rows)
if hint > initialLimit {
	hint = initialLimit
}
results := make([]Result, 0, hint)
```

**Use explicit capacity when:** a stable cardinality removes repeated growth
from a hot path. **Let growth work when:** the distribution has a long tail or
the collection is small. Manual growth can waste memory, copy more, and become
wrong as runtime behavior changes.

## Keep text in one representation

Ordinary `string(bytes)` and `[]byte(text)` conversions preserve value
semantics by copying data. Carry `[]byte` through parsing and I/O code, or
carry `string` through text code, instead of converting at every layer:

```go
func isRequestLine(line []byte) bool {
	return bytes.HasPrefix(line, []byte("GET "))
}
```

The compiler can use the byte slice transiently without a copy for a direct
string comparison, map lookup, or map deletion:

```go
if string(token) == "ready" {
	consume(token)
}

value, ok := table[string(token)]
delete(table, string(token))
```

That is a compiler optimization, not permission to retain mutable bytes as a
string. A map insertion must preserve the key after the byte slice changes,
so this conversion copies:

```go
table[string(token)] = value
```

Do not replace safe conversions with `unsafe.String` or `unsafe.Slice` unless
a profile proves the copy matters and the API can enforce immutability and
lifetime. A single mutation, append, pool return, or early reclamation can
turn the optimization into corrupted keys, races, or dangling data.

**Use one representation when:** adjacent layers already accept it and the
ownership contract stays simple. **Backfires when:** forcing `[]byte` through
text-oriented APIs spreads mutable aliasing, or conversion avoidance couples
otherwise clean package boundaries. Recheck on the deployed toolchain; these
elisions are not language guarantees.

## Build strings once

Repeated `+=` in a loop repeatedly copies the prefix. Use a builder and grow
it from a realistic size estimate:

```go
func join(parts []string, estimate int) string {
	var b strings.Builder
	if estimate > 0 {
		b.Grow(estimate)
	}
	for _, part := range parts {
		b.WriteString(part)
	}
	return b.String()
}
```

`strings.Builder.String` exposes the built bytes as an immutable string
without a final copy. Never copy a non-zero `Builder`. Use `bytes.Buffer`
instead when the consumer needs `[]byte`, `io.Reader`, or `io.Writer`
behavior.

**Use when:** several fragments form one retained string. **Backfires when:**
the estimate substantially overstates normal output, one concatenation would
already be clear and cheap, or callers need mutable bytes and immediately
convert the result back.

## Distinguish interface conversion from heap allocation

Putting a concrete value in an interface constructs an interface value. It
allocates backing storage only when the concrete data must escape its current
storage or another operation around the conversion allocates. Verify with
`-gcflags=-m=2` and `allocs/op`; do not equate every box with a heap object.

An escaping interface collection can make large value copies expensive:

```go
type Shape interface {
	Area() float64
}

func retain(dst []Shape, squares []Square) []Shape {
	for i := range squares {
		dst = append(dst, &squares[i])
	}
	return dst
}
```

Use `&squares[i]`, not `&square`, when identity must refer to the slice
element. The pointer form avoids copying a large value into interface storage,
but it retains the entire `squares` backing array, permits mutation through
aliases, adds indirection, and may move data to the heap. For small immutable
values, storing the value is often faster and simpler.

At an internal hot boundary with a stable type, a concrete function or a
generic helper can enable static dispatch. Keep interfaces where runtime
polymorphism, package boundaries, or testability justify them; compiler
devirtualization may already remove the indirect call.

**Use concrete or pointer forms when:** profiles attribute material copy,
dispatch, or escape cost to the interface path. **Backfires when:** the change
weakens the abstraction, retains a large owner, increases generated generic
code, or trades a cheap value copy for pointer chasing and GC scan work.

## Pool only proven temporary churn

Use `sync.Pool` for temporary, independently reusable objects shared across
many concurrent calls. Treat every `Get` as a cache miss: the runtime may
remove any pooled value at any time without notification.

```go
var bufferPool = sync.Pool{
	New: func() any { return new(bytes.Buffer) },
}

func encodeResponse(w io.Writer, v Value) error {
	b := bufferPool.Get().(*bytes.Buffer)
	b.Reset()
	defer func() {
		if b.Cap() <= 64<<10 {
			b.Reset()
			bufferPool.Put(b)
		}
	}()

	if err := encode(b, v); err != nil {
		return err
	}
	_, err := w.Write(b.Bytes())
	return err
}
```

Choose the retention cap from observed size percentiles and the service memory
budget; `64<<10` is only an example. Reset all logical state before reuse, and
clear sensitive bytes when confidentiality requires it. Nothing returned by
the operation may reference pooled storage after `Put`.

**Use when:** a profile shows repeated construction of similar temporary
objects under sustained concurrent load and a benchmark includes misses and
parallel use. **Backfires when:** objects are cheap, traffic is sparse, sizes
have outliers, cleanup has ownership semantics, callers retain aliases, or the
pool is mistaken for a cache with availability guarantees. Never copy a Pool
after first use.

## Lay out dense structs deliberately

The compiler inserts padding to meet each field's alignment. Group fields with
similar alignment, commonly larger-alignment fields before narrow scalars, in
types allocated in large arrays or copied frequently:

```go
type Sample struct {
	Timestamp int64
	Name      string
	Count     uint32
	Kind      uint16
	Ready     bool
}
```

Check the deployed architectures with `unsafe.Sizeof`, `unsafe.Alignof`, or a
layout analyzer. Pointer-containing headers also affect GC scan work; total
bytes are not the only metric.

**Use when:** many instances make padding visible in heap or cache profiles.
**Backfires when:** reordering breaks a binary/foreign-memory contract,
reflection or unsafe code depends on offsets, meaningful field grouping is
lost, or a singleton type gains no measurable benefit. Widest-first is a
heuristic, not a portable size proof.

## Separate contended fields only after proving false sharing

Independent atomics can invalidate the same cache line when different cores
write them. After a scaling benchmark identifies false sharing, isolate the
write-owned state using a cache-line size verified for the target:

```go
const cacheLine = 64 // target-specific; verify before relying on it

type paddedCounter struct {
	_     [cacheLine]byte
	value atomic.Int64
	_     [cacheLine]byte
}
```

Prefer ownership or sharding changes before padding: a worker-local counter
merged periodically often removes both sharing and atomic traffic.

**Use when:** throughput collapses as cores increase and hardware or controlled
benchmarks implicate cache coherence. **Backfires when:** fields are read-only,
written by the same goroutine, the assumed line size is wrong, or padding
inflates large arrays enough to harm locality and memory use.

## Make aliasing an ownership decision

Slicing is zero-allocation because the views share one backing array:

```go
func prefix(buf []byte, n int) []byte {
	if n > len(buf) {
		n = len(buf)
	}
	return buf[:n]
}
```

Use this only when the caller knows exactly how long the alias is valid and
who may mutate it. State contracts such as "valid until the next Read" in the
API. Copy before an asynchronous handoff, retention, mutation by another
owner, or pool return:

```go
owned := bytes.Clone(frame)
queue <- owned
```

**Use sharing when:** ownership is exclusive or immutability and lifetime are
enforced. **Backfires when:** an alias crosses a goroutine or package boundary,
the producer reuses storage, or retained capacity pins much more memory than
the visible value. Zero-copy is a paid optimization.

## Break accidental backing-store retention

A short slice or substring keeps its complete backing allocation reachable.
When a small result will outlive a large input, detach it:

```go
func retainFrame(readBuffer []byte, n int) []byte {
	return bytes.Clone(readBuffer[:n])
}

func retainName(record string, start, end int) string {
	return strings.Clone(record[start:end])
}
```

Limiting a slice's capacity does not release its backing array. Cloning does.
The same retention occurs in queues that repeatedly reslice from the front;
clear removed pointer elements and compact or replace the backing store when
retained capacity becomes material.

**Use when:** heap profiles show a large owner retained by small live views, or
the view crosses an ownership boundary. **Backfires when:** the view is
short-lived, most of the input remains useful, or the copy adds more churn
than the retained bytes cost. Decide from retained-heap profiles, not length
alone.

## Version compatibility

`strings.Clone` requires Go 1.18 and `bytes.Clone` requires Go 1.20. For an
older supported module, force an owned byte copy with
`append([]byte(nil), src...)`; detach a retained string with
`string(append([]byte(nil), src...))` only when that lifetime boundary requires
it. Typed atomic values in layout examples also depend on the module's Go
version. Preserve the repository minimum and test allocation behavior with the
exact deployed compiler.
