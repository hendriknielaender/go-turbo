# Priority Queues and Heaps

Reach for a heap when you need the extreme repeatedly rather than the whole
order.

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
