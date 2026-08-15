# Data Structures and Algorithms

The first performance question is whether the program is doing the right
amount of work. A better complexity class usually beats allocation tuning,
pooling, and instruction-level tricks while remaining easier to reason about.

## Contents

- [Choose by workload, not fashion](#choose-by-workload-not-fashion)
- [Map or small slice](#map-or-small-slice)
- [Sort once, query many times](#sort-once-query-many-times)
- [Priority queues and heaps](#priority-queues-and-heaps)
- [Monotonic stacks](#monotonic-stacks)
- [In-place transforms](#in-place-transforms)
- [Queues and rings](#queues-and-rings)
- [Pointer density and layout](#pointer-density-and-layout)
- [Measurement and review gates](#measurement-and-review-gates)

## Choose by workload, not fashion

Write down the operation mix and its bounds before choosing a representation:

- input size and its high percentile, not only its average;
- read, insert, delete, and iteration frequency;
- whether stable ordering is part of the contract;
- ownership, aliasing, and concurrent access;
- maximum retained memory and acceptable rejection behavior.

Big-O notation predicts scaling, not the winner for every size. Hashing,
indirection, cache misses, and allocation can make an asymptotically better
structure slower for a tiny bounded set. Conversely, a fast linear scan at
eight elements becomes an incident if an attacker can supply eight million.
Enforce the bound at the trust boundary when the choice depends on it.

Prefer a direct algorithmic fix when profiles show repeated work: index data
once instead of rescanning it, aggregate in one pass instead of sorting only
to count, and stop parsing once the answer is known. Preserve correctness for
duplicates, empty inputs, integer overflow, and adversarial ordering.

## Map or small slice

A map is the default for unbounded key lookup and uniqueness. A slice is often
the simpler representation for a small set that is mostly iterated, must keep
order, or is rebuilt as a unit. A linear slice scan has no hash computation
and reads contiguous memory; a map offers expected constant-time lookup but
has larger fixed costs and nondeterministic iteration order.

Do not encode a universal crossover point. Benchmark the real key type,
cardinality distribution, hit ratio, mutation pattern, and CPU architecture.
String hashing and integer comparison have different costs. A slice win at a
fixed size is invalid if production cardinality can grow without a hard cap.

```go
package lookup

type Entry struct {
	Key   uint32
	Value string
}

// Find is appropriate only while callers enforce a small maximum length.
func Find(entries []Entry, key uint32) (string, bool) {
	for i := range entries {
		if entries[i].Key == key {
			return entries[i].Value, true
		}
	}
	return "", false
}
```

Use a map when membership is the primary operation, deletes are common, or
the bound is not trustworthy. Use a sorted slice when updates are rare and
ordered iteration or range queries matter. Never depend on map iteration
order; sort keys explicitly when output must be stable.

## Sort once, query many times

Sorting costs `O(n log n)`, after which binary searches cost `O(log n)`.
That is attractive when a snapshot receives many queries. It is wasteful for
one query, and repeated insertion into the middle of a slice remains `O(n)`.
For mutable workloads, compare a map or a purpose-built tree rather than
silently paying copy costs.

Keep the comparator consistent with equality. Floating-point NaNs, locale
rules, and case folding can violate assumptions unless the domain defines an
ordering. When sorting shared data, copy it or transfer ownership; in-place
sorting is an observable mutation.

## Priority queues and heaps

Use a priority queue when the next minimum or maximum changes as items arrive:
scheduling by deadline, merging sorted streams, Dijkstra-style frontiers, or
maintaining the best `k` items. Go's `container/heap` operates through
`heap.Interface`; peek at index zero in constant time, while `Push`, `Pop`, and
`Fix` take logarithmic time. Building from an existing slice with `heap.Init`
is linear and is preferable to repeated insertion when all initial items are
already available.

Define ties explicitly. If equal priorities must retain arrival order, store a
monotonic sequence number and compare it after priority. For mutable priorities,
track each item's current index and call `heap.Fix`; an index becomes invalid
after removal. A lazy-deletion design can simplify updates, but stale entries
must have a memory bound and a cleanup policy.

For top-`k` selection, keep a heap of at most `k` elements rather than sorting
the complete input when `k` is much smaller than `n`. For a one-shot batch that
needs every result ordered, sorting is usually simpler. Benchmark realistic
`n`, `k`, update frequency, and comparator cost before replacing either.

The adapter's `Pop` should clear the removed tail element when it contains
pointers so the backing slice does not retain dead object graphs. A heap is not
concurrency-safe: guard the complete operation or confine ownership to one
goroutine. Atomics on the length or root do not make multi-step reordering safe.

## Monotonic stacks

A monotonic stack converts some nested scans into one pass. Typical cases ask
for the next greater or smaller element, span boundaries, or the largest
region constrained by local minima. Every index is pushed and popped at most
once, so the work is linear and the auxiliary storage is linear in the worst
case.

```go
package monotonic

// NextGreater returns the index of the first strictly greater value to the
// right, or -1. Equal values are deliberately not considered greater.
func NextGreater(values []int64) []int {
	result := make([]int, len(values))
	for i := range result {
		result[i] = -1
	}
	stack := make([]int, 0, len(values))
	for i, value := range values {
		for len(stack) != 0 && value > values[stack[len(stack)-1]] {
			j := stack[len(stack)-1]
			stack = stack[:len(stack)-1]
			result[j] = i
		}
		stack = append(stack, i)
	}
	return result
}
```

Specify strict versus non-strict comparison before writing the loop; changing
`>` to `>=` changes duplicate handling. Differential-test the optimized
algorithm against a plainly correct quadratic implementation on small random
inputs. This catches boundary errors more effectively than selected examples.

## In-place transforms

In-place compaction can remove an allocation when the caller owns the slice
and no alias needs the original contents. It is not a free win if mutation
breaks caller expectations or if retained elements keep large object graphs
alive. When elements contain pointers, clear positions beyond the returned
length so stale references in the backing array do not extend lifetimes.

```go
package compact

// KeepNonEmpty compacts values in place. The caller must own values and use
// the returned slice. Clearing the tail drops stale string-data references.
func KeepNonEmpty(values []string) []string {
	write := 0
	for _, value := range values {
		if value == "" {
			continue
		}
		values[write] = value
		write++
	}
	clear(values[write:])
	return values[:write]
}
```

`clear` removes references from the discarded slice positions; it does not
erase the bytes referenced by a string, force immediate reclamation, or affect
references held elsewhere. Another alias of the same backing array can still
observe the in-place writes, which is why exclusive ownership is part of the
function contract. The `clear` built-in requires Go 1.21; on an older supported
toolchain, assign the element type's zero value in a loop over the tail.

If input and output lifetimes differ, allocating a right-sized result can
retain less memory than returning a small subslice of a large backing array.
Choose ownership clarity first, then compare allocations and live heap.

## Queues and rings

Repeatedly removing `items[0]` and reslicing is logically constant time, but
the backing array and its pointer-bearing elements can stay live. Copying on
every pop avoids retention at `O(n)` cost. A bounded ring gives constant-time
push and pop, an explicit capacity budget, and stable storage.

```go
package ring

type Queue[T any] struct {
	buf        []T
	head, size int
}

func New[T any](capacity int) *Queue[T] {
	if capacity <= 0 {
		panic("ring capacity must be positive")
	}
	return &Queue[T]{buf: make([]T, capacity)}
}

// Push rejects when full; it never overwrites an unconsumed item.
func (q *Queue[T]) Push(value T) bool {
	if q.size == len(q.buf) {
		return false
	}
	index := (q.head + q.size) % len(q.buf)
	q.buf[index] = value
	q.size++
	return true
}

func (q *Queue[T]) Pop() (T, bool) {
	if q.size == 0 {
		var zero T
		return zero, false
	}
	value := q.buf[q.head]
	var zero T
	q.buf[q.head] = zero
	q.head = (q.head + 1) % len(q.buf)
	q.size--
	return value, true
}
```

This queue is not concurrency-safe. Put synchronization around the whole
operation or confine it to one goroutine; atomics added field-by-field do not
make a correct lock-free queue. Define whether a full queue rejects newest,
drops oldest, blocks, or times out. That policy is part of the API, not an
implementation detail.

A linked list is useful when stable node identity or constant-time removal
from a known node matters. It is usually poor for traversal-heavy queues:
every node adds allocation and pointer chasing. Measure before replacing a
slice or ring with one.

## Pointer density and layout

The garbage collector scans pointers, not arbitrary bytes. Pointer-rich
graphs also scatter accesses across cache lines. Prefer compact values and
contiguous slices when ownership permits. Keep large immutable payloads out
of per-item metadata, and consider separating hot fields from rarely used
diagnostic fields when profiles show cache or heap pressure.

Field ordering changes padding. For private structs, descending alignment or
width is a good first layout because it often removes holes; inspect the actual
size on each supported architecture. Do not blindly reorder public structs:
positional composite literals in other packages can break, serialized output
or binary layouts may depend on order, and atomic fields can have alignment
requirements. Group fields by
access pattern when cache locality matters more than minimum total size.
Pointer compression, structure-of-arrays layouts, and manual padding are paid
optimizations; they need benchmark or profile evidence and a comment naming
the maintenance tradeoff.

Values are not automatically cheaper than pointers. Copying a large struct
through a hot call chain can cost more than one well-owned pointer, while a
pointer per tiny element can multiply allocations. Let escape analysis,
`allocs/op`, and live-heap profiles decide.

## Measurement and review gates

For an algorithm or representation change:

1. Add property or differential tests covering empty, duplicate, maximum,
   and adversarial inputs.
2. Benchmark representative sizes, including the bound that triggers the
   design choice, with allocation reporting and repeated samples.
3. Profile the complete caller; a faster lookup is irrelevant if parsing or
   I/O dominates.
4. Inspect live memory, not only bytes allocated per operation. Retention can
   worsen while microbenchmark allocations improve.
5. Run the race detector for any ownership or synchronization change.

Keep the simpler structure when results overlap within noise. Complexity is
a production cost too, especially when an invariant must survive future edits.
