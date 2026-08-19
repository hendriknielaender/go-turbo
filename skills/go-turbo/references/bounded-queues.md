# Bounded Queues

A queue with no bound is a memory leak with a scheduler attached. Fix the size
from a latency budget rather than a round number, and decide what happens on
full before the queue exists.

A queue absorbs a finite mismatch between arrival and service rates. It cannot
fix sustained overload. Capacity must be fixed from a memory and latency
budget: queued work times worst-case retained bytes must fit, and queue wait
must leave enough deadline to execute.

A buffered channel is a useful bounded queue. Its capacity counts waiting
items only; active workers are additional concurrency. Keep one owner for
closing, never close from competing producers, and decide explicitly whether
submission blocks, times out, or rejects.

```go
package workqueue

import (
	"context"
	"errors"
)

var ErrFull = errors.New("work queue is full")

type Queue[T any] struct {
	items chan T
}

func New[T any](capacity int) *Queue[T] {
	if capacity <= 0 {
		panic("queue capacity must be positive")
	}
	return &Queue[T]{items: make(chan T, capacity)}
}

func (q *Queue[T]) TrySubmit(value T) error {
	select {
	case q.items <- value:
		return nil
	default:
		return ErrFull
	}
}

func (q *Queue[T]) Receive(ctx context.Context) (T, error) {
	// Do not consume an item when shutdown was already requested at entry.
	if err := ctx.Err(); err != nil {
		var zero T
		return zero, err
	}
	select {
	case value := <-q.items:
		return value, nil
	case <-ctx.Done():
		var zero T
		return zero, ctx.Err()
	}
}
```

This example intentionally has no `Close`; lifecycle ownership differs by
service, and receiving from a closed channel without checking the second
result would fabricate zero-value work forever. Production shutdown must stop
admission, drain or cancel according to contract, then stop workers.

`Receive` gives cancellation priority only when the context is already done at
entry. If an item and cancellation become ready together after that check, Go
may select either. A returned item has transferred to the caller and must be
processed or explicitly discarded under the shutdown policy; the method does
not silently dequeue and return cancellation. Services requiring a strict
drain boundary should stop producers first and have the queue owner close a
separate admission state before canceling workers.

Queue metrics need capacity, depth, oldest-item age, rejection count, and time
spent waiting. Depth alone misses a small queue whose oldest item already
exceeded its deadline. Drop expired work before execution and make that outcome
visible.
