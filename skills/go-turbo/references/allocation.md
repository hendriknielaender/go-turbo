# Allocation

Allocation is the dominant performance tax in most Go programs. Every heap
object is paid for twice: once at the allocator, and again at every GC cycle
that has to mark and sweep it. `allocs/op` is the single most useful number
in a Go benchmark because it is nearly deterministic — it doesn't wobble with
machine load the way `ns/op` does, and a change in it almost always explains
a change in throughput.

## Contents

- [Preallocation](#preallocation)
- [Slice growth](#slice-growth)
- [String and []byte conversion](#string-and-byte-conversion)
- [Object pooling with sync.Pool](#object-pooling-with-syncpool)
- [Interface boxing](#interface-boxing)
- [Struct layout and padding](#struct-layout-and-padding)
- [False sharing](#false-sharing)
- [Zero-copy slicing](#zero-copy-slicing)
- [The retained-backing-array leak](#the-retained-backing-array-leak)

## Preallocation

When the final size is known or boundable, give `make` the capacity. This is
a free win: same code shape, fewer allocations, no readability cost.

```go
// Repeated reallocation and copying as the slice grows.
var out []Result
for _, r := range rows {
    out = append(out, convert(r))
}

// One allocation.
out := make([]Result, 0, len(rows))
for _, r := range rows {
    out = append(out, convert(r))
}
```

If every element gets written, index instead of appending — it skips the
append bookkeeping entirely:

```go
out := make([]Result, len(rows))
for i, r := range rows {
    out[i] = convert(r)
}
```

Maps take a size hint too, which pre-sizes the internal table and avoids
incremental rehashing:

```go
m := make(map[string]int, len(keys))
```

**When not to.** Preallocating a capacity you don't fill is not free — it is
memory you hold, memory the GC scans, and cache lines you waste. If input
sizes vary by orders of magnitude, size for the common case and let `append`
handle the tail. Reserving the worst case "to be safe" reliably makes things
slower, and is the single most common way C++ habits misfire in Go.

## Slice growth

`append` grows the backing array geometrically: doubling below a threshold of
256 elements, then tapering toward ~25% growth for large slices. On a current
toolchain the sequence runs `… 128 → 256 → 512 → 848 → 1280 → 1792 …` — clean
doubling, then a smooth taper. (The exact thresholds have shifted across
releases; the shape is stable.) This is well tuned. Without a known final
size, hand-rolled growth strategies usually lose to it.

What actually costs you is the copy on each growth. For a slice that ends at
n elements from a zero-capacity start, you allocate O(log n) times and copy
O(n) elements total. Preallocation turns that into one allocation and zero
copies — which is why it matters most for large slices, and barely at all for
slices of a handful of items.

## String and []byte conversion

`[]byte(s)` and `string(b)` copy. In a hot loop, the round trip is often the
allocation you're looking for.

```go
// Allocates on every iteration.
for _, line := range lines {
    if strings.HasPrefix(string(line), "GET ") { ... }
}

// No allocation: bytes has the same API surface.
for _, line := range lines {
    if bytes.HasPrefix(line, []byte("GET ")) { ... }
}
```

Pick one representation and carry it end to end rather than converting at
each layer boundary. `bytes` mirrors `strings` closely enough that staying in
`[]byte` for I/O paths costs almost nothing in readability.

Conversions the compiler already elides — no workaround needed:

- `string(b)` used only as a map key: `m[string(b)]`
- `string(b)` compared directly: `if string(b) == "GET"`
- ranging over `string(b)`: `for _, r := range string(b)`

Building strings:

```go
// Quadratic: each += allocates a new string and copies everything so far.
s := ""
for _, part := range parts {
    s += part
}

// Linear, one or two allocations.
var b strings.Builder
b.Grow(estimatedSize)
for _, part := range parts {
    b.WriteString(part)
}
s := b.String()
```

`strings.Builder.String()` does not copy — it hands over the accumulated
buffer, which is why `Builder` beats `bytes.Buffer` when the result is a
string.

## Object pooling with sync.Pool

`sync.Pool` recycles objects across calls so the allocator and GC never see
them. It works best for short-lived, uniformly-sized scratch objects on a
genuinely hot path: request buffers, encoders, scratch slices.

```go
var bufPool = sync.Pool{
    New: func() any { return new(bytes.Buffer) },
}

func handle(w http.ResponseWriter, r *http.Request) {
    buf := bufPool.Get().(*bytes.Buffer)
    buf.Reset()          // reposition; the backing array is kept
    defer bufPool.Put(buf)

    encode(buf, r)
    w.Write(buf.Bytes())
}
```

The win comes from `Reset()` keeping the backing array. After the pool warms
up, `Get` returns a buffer already large enough for the workload and writes
land in existing memory — steady-state allocation for the buffer drops to
zero.

**This is a paid win.** What you are buying it with:

- **Lifetime bugs.** Anything retaining a reference after `Put` reads memory
  that another goroutine is now writing. This is the classic `sync.Pool` bug
  and it is a data race, not a glitch.
- **Reset discipline.** Forget to reset and you leak the previous caller's
  data into the next response. For anything holding user data, that is a
  security bug, not a performance one.
- **Unbounded retention.** Pooling variable-sized buffers keeps the largest
  one ever seen alive indefinitely. Cap it:

```go
func put(b *bytes.Buffer) {
    if b.Cap() > 64<<10 { // don't retain outliers
        return
    }
    b.Reset()
    bufPool.Put(b)
}
```

**When not to pool.** Long-lived objects (the GC handles those fine),
low-churn paths (the pool costs more than it saves), objects with real
teardown semantics, and anything where you can't guarantee no reference
survives `Put`. A pool that isn't hit hard is a memory leak with extra steps.

Note that pooled objects are cleared at GC, so a pool is a throughput
optimization for sustained load, not a cache.

## Interface boxing

Assigning a concrete value to an interface stores a type descriptor plus a
data pointer. When the value isn't already on the heap, that assignment
allocates a copy.

```go
type Shape interface{ Area() float64 }

shapes := make([]Shape, 0, len(squares))
for _, s := range squares {
    shapes = append(shapes, s)  // copies the whole struct into a new allocation
}
```

For a large struct, that copies the entire value on every append. Boxing a
pointer copies eight bytes instead:

```go
for i := range squares {
    shapes = append(shapes, &squares[i])
}
```

Note `&squares[i]` rather than `&s` — a loop variable's address is not the
element's address, and taking it forces the copy you were avoiding. (Go 1.22+
gives each iteration its own variable, which makes `&s` safe but still a
copy.)

Small values (`int`, `float64`) still allocate when boxed — the runtime has
not inlined values into interfaces since Go 1.4 — but the cost is small
enough to ignore outside tight loops. In a profile, boxing shows up as
`runtime.convT*` allocations.

**When boxing is right:** anywhere the abstraction earns its keep. Interfaces
at package boundaries, `io.Reader`/`io.Writer`, test seams, runtime
polymorphism. Avoid interfaces in hot inner loops where the concrete type is
known and stable; keep them everywhere else. Note also that a value in an
interface can't be inlined through, so a hot call through an interface pays
an indirect call plus the lost inlining, not just the boxing.

## Struct layout and padding

Fields are aligned to their own width, and the compiler inserts padding to
satisfy that. Field order therefore changes the size of every instance.

```go
// 24 bytes: 1 byte + 7 padding + 8 + 1 + 7 padding
type Poorly struct {
    Flag  bool
    Count int64
    Small uint8
}

// 16 bytes: 8 + 1 + 1 + 6 padding
type Well struct {
    Count int64
    Flag  bool
    Small uint8
}
```

At a million instances that is 8 MB of pure padding, plus the cache lines
wasted moving it around. Reordering is free — no logic changes — so order
fields widest-first by default: pointers and 8-byte scalars, then 4, then 2,
then bools and single bytes, with strings and slices (which are multi-word
headers) grouped near the top.

`fieldalignment` (in `golang.org/x/tools/go/analysis/passes/fieldalignment`,
also available through `go vet -vettool` and most linter aggregators) finds
these automatically. Worth wiring into CI once.

Don't reorder when it destroys a meaningful grouping in a struct that is
never allocated in bulk — a config struct instantiated once doesn't care.

## False sharing

A cache line is 64 bytes on mainstream CPUs. Two fields in the same line are,
as far as the coherence protocol is concerned, one unit: if goroutine A
writes field X on core 1, core 2's copy of the line is invalidated, so
goroutine B's read of unrelated field Y stalls.

```go
// Both counters land in one cache line: every write to one stalls the other.
type Counters struct {
    A atomic.Int64
    B atomic.Int64
}

// Padded to separate lines.
type Counters struct {
    A atomic.Int64
    _ [56]byte
    B atomic.Int64
    _ [56]byte
}
```

This only matters for fields written frequently by different goroutines —
per-core counters, sharded state, ring buffer head/tail indices. Padding
everything wastes memory for nothing. Reach for it when a benchmark shows a
concurrent counter or sharded structure scaling badly with core count, not
preemptively.

## Zero-copy slicing

Slicing shares the backing array; no copy, no allocation.

```go
func header(buf []byte) []byte {
    return buf[:8]   // free
}
```

This is genuinely free when the data is read-only for its whole lifetime and
the sub-slice does not outlive the buffer. It is a paid win the moment either
of those is uncertain, because you have created aliasing: whoever writes
through one view changes what the other sees.

Two rules keep it safe:

1. Document ownership at the function boundary — "the returned slice aliases
   `buf` and is valid until the next `Read`" — or copy.
2. Copy before handing data to anything that might retain it (see below).

`io.CopyBuffer` is the same idea for streams: it reuses one caller-supplied
buffer rather than allocating per copy.

```go
func stream(dst io.Writer, src io.Reader) error {
    buf := make([]byte, 32*1024) // or from a pool
    _, err := io.CopyBuffer(dst, src, buf)
    return err
}
```

Note that `io.CopyBuffer` ignores the buffer if `src` implements `WriterTo`
or `dst` implements `ReaderFrom` — those paths are already efficient.

## The retained-backing-array leak

A sub-slice keeps the *entire* backing array alive, not just the visible
window. This is the most common memory leak in connection-handling code.

```go
buf := pool.Get().([]byte)      // 32 KB
n, _ := conn.Read(buf)

data := buf[:n]                 // n might be 12
queue <- data                   // 32 KB stays reachable, per message
```

Across thousands of connections this retains hundreds of megabytes that
`pprof` will attribute to the pool, not the queue. Copy when handing off:

```go
data := make([]byte, n)
copy(data, buf[:n])
queue <- data
```

The copy is cheap; the retention is not. Same trap applies to
`slice = slice[1:]` in a queue implementation — the dropped prefix stays
alive — and to holding a small substring of a large string.
