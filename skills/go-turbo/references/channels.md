# Channels and Value Ownership

A channel transfers ownership as well as a value. Most channel bugs are
ownership left unstated.

Choose channel capacity from semantics:

- unbuffered channels require sender and receiver to rendezvous;
- bounded buffers absorb a known burst and then apply backpressure;
- closing is a sender-owned broadcast that no more values will arrive.

Capacity is retained memory, not free throughput. An oversized channel hides
overload until latency and memory have already grown. An unbounded queue built
around a slice merely moves the eventual failure.

A channel transfers its element by value. Large structs enlarge buffered
channel storage and can make copying material. A pointer is not an automatic
fix: it can force an escape, adds GC-visible indirection, extends the object's
lifetime, and can introduce a race if sender and receiver both mutate it.
Prefer a small immutable value, an identifier, or an explicit ownership token.
Send a pointer when the object already has a suitable lifetime and ownership is
unambiguous, then benchmark. Never return a pooled object until the receiver is
finished with it.

Non-blocking sends are appropriate only when loss is intentional and counted:

```go
select {
case samples <- sample:
default:
	dropped.Add(1)
}
```

For a hot counter, an atomic is normally cheaper than sending every increment
to a collector goroutine. For a queue, include cancellation in both send and
receive paths.
