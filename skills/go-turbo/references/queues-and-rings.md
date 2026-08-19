# Queues and Rings

A ring buffer when the queue is bounded and the churn is high; a slice when it
is neither.

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
