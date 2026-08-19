# Batching Across Boundaries

A batch turns N boundary crossings into one, and the rule that makes it safe is
that no lock may be held across the I/O. Group work at the remote boundary —
queries, RPCs, writes — and keep the critical section off the wire.

## Batch without holding locks across I/O

Batching amortizes fixed cost, but it creates queueing latency and a crash-loss
window. The batch contract must state its flush trigger, hard item and byte
bounds, maximum wait, ordering, and delivery semantics.

Never call a database, RPC, or user callback while holding the mutex that
protects the producer buffer. Detach the current slice under the lock, install
a different backing array, and flush the detached batch outside that lock.
Serialize flushes if ordering matters.

```go
type Batcher[T any] struct {
	mu      sync.Mutex
	flushMu sync.Mutex
	buf     []T
	spare   []T
	flushAt int
	write   func(context.Context, []T) error
}

func NewBatcher[T any](
	flushAt int,
	write func(context.Context, []T) error,
) (*Batcher[T], error) {
	if flushAt < 1 {
		return nil, fmt.Errorf("flush trigger must be positive: %d", flushAt)
	}
	if write == nil {
		return nil, errors.New("batch writer is nil")
	}
	return &Batcher[T]{
		buf:     make([]T, 0, flushAt),
		spare:   make([]T, 0, flushAt),
		flushAt: flushAt,
		write:   write,
	}, nil
}

func (b *Batcher[T]) Add(ctx context.Context, item T) error {
	if err := ctx.Err(); err != nil {
		return err
	}

	b.mu.Lock()
	b.buf = append(b.buf, item)
	full := len(b.buf) >= b.flushAt
	b.mu.Unlock()
	if !full {
		return nil
	}
	return b.Flush(ctx)
}

func (b *Batcher[T]) Flush(ctx context.Context) error {
	// Serialize detach plus delivery so batches cannot overtake one another.
	b.flushMu.Lock()
	defer b.flushMu.Unlock()

	b.mu.Lock()
	if len(b.buf) == 0 {
		b.mu.Unlock()
		return nil
	}
	batch := b.buf
	b.buf = b.spare[:0]
	b.spare = nil
	b.mu.Unlock()

	// write must not retain batch after returning; clone there if it must.
	err := b.write(ctx, batch)

	clear(batch) // release pointers before retaining the backing array
	b.mu.Lock()
	if cap(batch) == b.flushAt {
		b.spare = batch[:0]
	} else {
		// Do not retain a backing array grown by an unusual concurrent burst.
		b.spare = make([]T, 0, b.flushAt)
	}
	b.mu.Unlock()
	return err
}

func (b *Batcher[T]) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		return fmt.Errorf("flush interval must be positive: %s", interval)
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return context.Cause(ctx)
		case <-ticker.C:
			if err := b.Flush(ctx); err != nil {
				return err
			}
		}
	}
}
```

This design is safe for concurrent `Add` and `Flush`, does not expose a slice
that producers continue to mutate, serializes callbacks, propagates callback
errors, and stops its ticker. Producers may append while a slow flush runs, so
the trigger is not a hard queue bound. Bound their concurrency and add a byte
limit or a bounded input channel when item sizes or producer counts vary.

Run the timer loop under supervision and treat its returned error as fatal to
the batching pipeline. `Add` likewise returns a size-triggered flush error to
its caller. On shutdown, cancel and join producers, stop `Run`, then call
`Flush` with a new bounded shutdown context. The canceled run context is not a
usable flush context.

The writer owns the detached batch for the duration of its call. On error, the
batcher does not blindly requeue it because the writer may have committed a
prefix. The writer must provide transactional or idempotent semantics when
retries are required. Persist before acknowledging if process-crash loss is
unacceptable. The writer must not call `Add` or `Flush` on the same batcher;
flushes are serialized and such re-entry can deadlock. Run exactly one timer
loop per batcher.

For databases, use the driver's real bulk facility or a transaction with
prepared statements; concatenating SQL is neither a safe nor necessarily fast
batch. For sockets that support scatter/gather, `net.Buffers.WriteTo` may map
several byte slices to an OS-specific vector write without first concatenating
them. `WriteTo` consumes the `net.Buffers` slice headers, so reconstruct that
slice before reuse; it does not mutate the payload bytes.
