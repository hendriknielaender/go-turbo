# Caller-Owned Buffers

`AppendX(dst []byte, …) []byte` moves the allocation decision to the caller, which
is where the lifetime knowledge already lives.

## Give callers control of reusable storage

Append into caller-owned capacity instead of returning a fresh buffer from a
hot operation:

```go
func AppendRecord(dst []byte, r Record) []byte {
	dst = append(dst, r.Kind...)
	dst = append(dst, ':')
	return strconv.AppendInt(dst, r.Count, 10)
}
```

The caller can keep one buffer across a loop and the callee can remain
allocation-free until capacity grows.

**Use when:** the API is internal or append semantics are natural and callers
already batch work. **Backfires when:** a caller assumes the result is
independent, retains multiple returned views, or threading scratch state
through many layers damages the API for a cold-path allocation.

Document whether the result aliases `dst`. If independent results are needed,
clone at the ownership boundary.

## Reuse storage without violating ownership

Hoist a scratch buffer out of a loop and reset its length:

```go
buf := make([]byte, 0, 256)
for _, item := range items {
	buf = buf[:0]
	buf = encodeItem(buf, item)
	consumeNow(buf)
}
```

This is valid only when `consumeNow` finishes with the bytes before the next
iteration. If it stores, queues, or launches work with the slice, clone before
reuse. Reuse can otherwise produce silent data corruption as well as a race.

**Use when:** processing is synchronous and size is stable. **Backfires when:**
capacity retains rare outliers, ownership is unclear, or concurrency turns one
scratch buffer into shared mutable state. Apply a measured capacity cap or let
an outlier buffer go.
