# Mutexes and Atomics

Reach for the cheapest coordination the ownership model allows. Most reported
lock overhead is work that did not need to be inside the critical section.

## Mutexes, atomics, and ownership

The cheapest synchronization is exclusive ownership: keep mutable state in one
goroutine or partition it so concurrent workers never touch the same object.
When sharing is required, choose the simplest primitive that preserves the
invariant.

- `sync.Mutex`: multiple fields or a multi-step invariant.
- `sync.RWMutex`: only after a benchmark demonstrates that parallel, long
  reads outweigh its additional bookkeeping. It cannot be upgraded or
  downgraded.
- typed `sync/atomic` values: one independent word such as a counter, flag, or
  immutable pointer.
- channels: coordination and ownership transfer, not a faster mutex.

Go's atomic operations are sequentially consistent. An atomic flag does not
make adjacent non-atomic state safe. Publish an entire immutable object through
an `atomic.Pointer[T]`, or protect the complete invariant with a lock.

```go
type Counters struct {
	requests atomic.Uint64
	failures atomic.Uint64
}

func (c *Counters) Record(err error) {
	c.requests.Add(1)
	if err != nil {
		c.failures.Add(1)
	}
}
```

Typed atomic values and lock types must not be copied after first use. A single
heavily updated atomic can itself become a cache-coherence bottleneck; shard or
aggregate per worker only after contention is visible in measurements.

Use `CompareAndSwap` when the operation is a claim, not a separate observation
and update:

```go
if !started.CompareAndSwap(false, true) {
	return
}
startOnce()
```

Do not turn a multi-state protocol into a clever CAS loop without tests for
all transitions, cancellation, and ABA/lifetime hazards. A clear mutex is
usually faster to maintain and often fast enough to run.
