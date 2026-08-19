# Memory Layout and Aliasing

Layout matters at volume and almost nowhere else. Padding, false sharing, and
aliasing are measured concerns — and exported, encoded, reflected, cgo, and
`unsafe`-observed layouts are compatibility boundaries, not free variables.

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
