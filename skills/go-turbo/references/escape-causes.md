# Common Escape Causes

The code shapes that push a value to the heap, and the compiler behaviour that
changes which of them still apply.

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
