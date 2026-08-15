# Escape Analysis

Escape analysis decides whether storage may remain in a stack frame or must
survive elsewhere. Stack placement removes heap allocation and GC work, but it
is not a goal by itself: stacks consume memory, grow by copying, and can make
large or recursive frames expensive. Fix incidental escapes only where a
representative measurement says they matter.

## Contents

- [Read the compiler's decision](#read-the-compilers-decision)
- [Reason about lifetime, not syntax](#reason-about-lifetime-not-syntax)
- [Recognize common escape paths](#recognize-common-escape-paths)
- [Account for Go 1.26 slice placement](#account-for-go-126-slice-placement)
- [Give callers control of reusable storage](#give-callers-control-of-reusable-storage)
- [Prefer values when values express the semantics](#prefer-values-when-values-express-the-semantics)
- [Use bounded stack scratch deliberately](#use-bounded-stack-scratch-deliberately)
- [Reuse storage without violating ownership](#reuse-storage-without-violating-ownership)
- [Keep hot dispatch visible when evidence supports it](#keep-hot-dispatch-visible-when-evidence-supports-it)
- [Treat inlining and escape analysis as coupled evidence](#treat-inlining-and-escape-analysis-as-coupled-evidence)
- [Leave necessary escapes alone](#leave-necessary-escapes-alone)
- [Verify the shipped build](#verify-the-shipped-build)

## Read the compiler's decision

Inspect the package first; inspect dependencies only when a boundary remains
unexplained:

```sh
go build -gcflags='-m=2' ./path/to/pkg
go test -c -gcflags='-m=2' ./path/to/pkg
go build -gcflags='all=-m=2' ./path/to/pkg
```

The verbose form prints inlining decisions and the data-flow reason for an
escape. Useful messages include:

```text
moved to heap: x
&T{...} escapes to heap
parameter p leaks to ~r0
argument does not escape
inlining call to f
```

`leaks to` describes a relationship between a parameter and a result or
stored location; it does not prove that every call allocates. Likewise, `does
not escape` says nothing about allocations performed elsewhere in the
function. Trace the reasoning chain to the value reported by `allocs/op` or an
allocation profile.

Compiler diagnostics are not a stable API. Wording and placement decisions
can change with Go version, architecture, build tags, instrumentation, PGO,
and surrounding code.

**Use when:** a profile or benchmark identifies a hot allocation and its
source is unclear. **Backfires when:** teams treat every diagnostic as a bug,
or tests assert exact diagnostic text and break on harmless compiler changes.

## Reason about lifetime, not syntax

Taking an address, calling `new`, using a pointer receiver, or converting to
an interface does not inherently allocate. Storage moves to the heap when the
compiler cannot prove that all references die within a safe stack lifetime.

Returning a pointer requires the object to outlive an out-of-line call:

```go
func newConfig() *Config {
	return &Config{}
}
```

That constructor is correct. If it is inlined and the caller does not retain
the result, the compiler may still place the object on the caller's stack.
Judge the call site and shipped binary, not the token `&`.

The compiler also records escape summaries for non-inlined functions. A
pointer argument does not automatically escape merely because the call stayed
out of line.

## Recognize common escape paths

### Store a pointer in longer-lived state

Globals, returned objects, heap-resident fields, channels, and asynchronous
work often extend a pointee's lifetime:

```go
var current *Entry

func publish() {
	e := Entry{}
	current = &e
}
```

This escape is required by the program's semantics. Remove it only by changing
ownership or lifetime, not by obscuring the pointer from the compiler.

### Capture data in work that outlives the call

Returned closures and goroutines commonly retain captured variables:

```go
func counter() func() int {
	n := 0
	return func() int {
		n++
		return n
	}
}
```

An immediately invoked closure can remain stack-local. Prefer passing
goroutine inputs as explicit parameters when that clarifies ownership, but do
not expect the rewrite alone to remove an escape; asynchronous lifetime still
requires reachable storage.

### Retain an iteration variable's address

With Go 1.22 or newer language semantics, a range variable declared by the
loop is distinct on each iteration. Retaining `&value` is therefore correct,
but it retains a per-iteration copy and can create one heap object per item.
When callers need identity with the source slice, address the element:

```go
func itemPointers(items []Item) []*Item {
	result := make([]*Item, 0, len(items))
	for i := range items {
		result = append(result, &items[i])
	}
	return result
}
```

This form can keep the complete source backing array live and exposes its
elements to mutation. Use values instead when identity is unnecessary. Check
the module's language version when reviewing code that may retain range
variables; older semantics differ.

### Hide lifetime behind dynamic behavior

Interface calls, function values, reflection, and `...any` can reduce the
compiler's knowledge of the callee. The interface conversion itself allocates
only if its concrete data escapes. Formatting APIs may also allocate their own
buffers, so attribute the cost before replacing them.

For a measured integer-formatting loop, an append-style path can keep storage
with the caller:

```go
func appendID(dst []byte, id int64) []byte {
	dst = append(dst, "id="...)
	return strconv.AppendInt(dst, id, 10)
}
```

This backfires on cold error and logging paths where `fmt` is clearer and its
cost is irrelevant.

### Exceed a stack-placement constraint

The compiler may reject a stack candidate because its size is large,
unbounded, or unsuitable for a frame. These are implementation constraints,
not language constants. Avoid documenting or coding against an exact byte or
inlining budget.

Shrinking an object can help only when the profile attributes cost to that
object. Splitting it into pointers may reduce a copy while adding allocations,
indirections, and GC scan work.

## Account for Go 1.26 slice placement

Go 1.26 can stack-place more non-escaping slice backing stores even when the
requested length or capacity is not a source-level constant. The compiler can
generate a bounded stack-backed path and a heap fallback for larger runtime
sizes. It can also recover constants through local data flow.

Do not assume that this allocates:

```go
func checksum(n int) byte {
	b := make([]byte, n)
	fill(b)
	return fold(b)
}
```

Inspect `-m=2` and `allocs/op` for the exact call distribution. If `n` is
usually above the compiler's internal bound, the heap fallback remains. If
the slice escapes through `fill` or `fold`, stack placement is unavailable.

**Use the compiler-provided path when:** the slice is local and bounded in
practice. **Backfires when:** code adds a second manual scratch array based on
an assumed compiler threshold, inflating frames while preserving the fallback
allocation. Compiler thresholds are deliberately not contractual.

## Give callers control of reusable storage

Append into caller-owned capacity instead of returning a fresh buffer from a
hot operation:

```go
func AppendRecord(dst []byte, r Record) []byte {
	dst = append(dst, r.Kind...)
	dst = append(dst, ':')
	return strconv.AppendInt(dst, r.Count, 10)
}
```

The caller can keep one buffer across a loop and the callee can remain
allocation-free until capacity grows.

**Use when:** the API is internal or append semantics are natural and callers
already batch work. **Backfires when:** a caller assumes the result is
independent, retains multiple returned views, or threading scratch state
through many layers damages the API for a cold-path allocation.

Document whether the result aliases `dst`. If independent results are needed,
clone at the ownership boundary.

## Prefer values when values express the semantics

Return and pass small immutable structs by value unless mutation, identity, or
nil has meaning:

```go
func parseHeader(src []byte) (Header, error) {
	var h Header
	if err := decodeHeader(&h, src); err != nil {
		return Header{}, err
	}
	return h, nil
}
```

Registers and stack copies often make this cheaper than allocating a separate
object and chasing a pointer. The compiler may remove copies entirely.

**Use when:** the type is modest, copy semantics are correct, and benchmarks
show pointer construction or GC pressure. **Backfires when:** the struct is
large or copied frequently, contains synchronization primitives that must not
be copied, requires stable identity, or value semantics obscure mutation.

## Use bounded stack scratch deliberately

For a small protocol maximum, use a local array and slice it:

```go
func appendNumber(dst []byte, n int64) []byte {
	var scratch [32]byte
	tmp := strconv.AppendInt(scratch[:0], n, 10)
	return append(dst, tmp...)
}
```

The returned `dst` owns the copied bytes; the local scratch does not escape.
Prefer this shape only when the bound is inherent and the compiler is not
already producing an equivalent stack path.

**Use when:** a fixed small maximum is part of the format and a benchmark
removes a hot allocation. **Backfires when:** large arrays increase stack
growth and copying, recursion multiplies frame cost, the bound is guessed, or
the resulting slice escapes and moves the array to the heap anyway.

## Reuse storage without violating ownership

Hoist a scratch buffer out of a loop and reset its length:

```go
buf := make([]byte, 0, 256)
for _, item := range items {
	buf = buf[:0]
	buf = encodeItem(buf, item)
	consumeNow(buf)
}
```

This is valid only when `consumeNow` finishes with the bytes before the next
iteration. If it stores, queues, or launches work with the slice, clone before
reuse. Reuse can otherwise produce silent data corruption as well as a race.

**Use when:** processing is synchronous and size is stable. **Backfires when:**
capacity retains rare outliers, ownership is unclear, or concurrency turns one
scratch buffer into shared mutable state. Apply a measured capacity cap or let
an outlier buffer go.

## Keep hot dispatch visible when evidence supports it

A concrete internal helper can expose callee behavior and static dispatch:

```go
func writeBatch(w *bufio.Writer, records []Record) error {
	for _, record := range records {
		if _, err := w.WriteString(record.Name); err != nil {
			return err
		}
	}
	return nil
}
```

Keep an interface at the public boundary and adapt once outside the hot loop
when the concrete implementation is truly fixed. A generic helper is another
option, but it can increase build time and binary size and does not guarantee
inlining.

**Use when:** a profile shows indirect-call or escape cost and the internal
type is stable. **Backfires when:** it couples packages, duplicates paths for
several implementations, or the compiler already devirtualizes the call.

## Treat inlining and escape analysis as coupled evidence

Inlining can expose caller-specific lifetimes and constant values; escape
summaries can preserve useful facts even when a call is not inlined. Ask the
compiler what happened:

```sh
go build -gcflags='-m=2' ./path/to/pkg 2>&1 | rg 'inline|escape|heap'
```

If a hot wrapper is not inlined, keep its common path small and move uncommon
error or setup work into a helper. Do not depend on a fixed compiler budget or
assume a particular statement is always an inlining blocker.

**Use when:** profiles show a very frequent call and diagnostics connect
inlining to a real allocation or dispatch cost. **Backfires when:** splitting
fragments cohesive logic, grows code and instruction-cache pressure, or PGO
and a newer toolchain already make the desired decision.

## Leave necessary escapes alone

Keep heap allocation when any of these is true:

- The object genuinely outlives the call: cache entry, shared state,
  asynchronous message, or returned mutable identity.
- A constructor runs rarely and pointer semantics make the API clearer.
- Avoiding the escape requires pervasive scratch parameters, unsafe aliases,
  or an object pool without measured benefit.
- A large object is safer and cheaper on the heap than in many growing or
  recursive stacks.
- The allocation is absent from representative profiles.

`sync.Pool` does not make an object stack allocated; it amortizes heap objects
and adds a lifetime protocol. Use it only under the conditions in
`allocation.md`.

For finalizers, cleanups, cgo handles, or syscalls that use a resource after
the compiler's last visible reference, place `runtime.KeepAlive` after the
last operation that requires the owner. Do not use `KeepAlive` to conceal an
ordinary ownership error.

## Verify the shipped build

After a source-level fix:

1. Build with the production Go version, tags, PGO profile, and architecture.
2. Confirm the intended decision with `-m=2`.
3. Run the focused benchmark with `-benchmem -count=10` and compare with
   `benchstat`.
4. Recheck the allocation profile under representative load.
5. Run correctness tests and `-race` for any ownership or concurrency change.

Race and sanitizer instrumentation can change escape and conversion behavior;
run them for correctness, then measure the production-shaped binary
separately. Keep the optimization only if the number improves and its
ownership rules remain understandable.
