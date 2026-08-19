# Object Lifetime APIs

Weak pointers, cleanups, and forced collection express lifetime *semantics*, not
eviction policy. Reach for them when the relationship between two objects is the
thing you are modelling — and keep `Close` explicit regardless.

## Force collection or scavenging only at explicit phase boundaries

`runtime.GC` forces a complete collection and blocks the caller; it may also
block the whole program. `debug.FreeOSMemory` forces a collection and then asks
the scavenger to return as much memory as possible to the OS. The runtime
already scavenges unused pages in the background.

**Use when:** a test requires a collection boundary, a diagnostic needs a
repeatable heap state, or a measured batch program finishes a known large
phase and can tolerate the latency. **Backfires when:** invoked from request
paths, timers, or memory watchdogs; repeated forcing adds pauses, CPU, and page
faults when memory is needed again. Fix retention and set a budget instead of
turning forced GC into policy.

## Use weak pointers for lifetime semantics, not deterministic eviction

`weak.Pointer[T]` does not keep its target reachable. `Value` may become nil as
soon as the target is unreachable, and collection timing is unspecified:

```go
type Registry struct {
	mu sync.Mutex
	m  map[string]weak.Pointer[Entry]
}

func (r *Registry) Lookup(key string) *Entry {
	r.mu.Lock()
	defer r.mu.Unlock()

	p, ok := r.m[key]
	if !ok {
		return nil
	}
	entry := p.Value()
	if entry == nil {
		delete(r.m, key)
	}
	return entry
}
```

Use weak pointers for canonicalization, identity relationships, or caches that
must not extend an object's lifetime. The returned pointer is a normal strong
reference while reachable.

**Backfire cases:** hit rate follows GC timing, stale map keys remain until
maintenance or lookup, recreating a value can break identity expectations,
and weak references complicate concurrency. Use an explicitly size-bounded
cache for predictable capacity and eviction. Never use weak reachability as a
correctness or resource-release signal.

## Keep cleanup nondeterministic and Close explicit

Release files, sockets, transactions, mappings, and buffers through explicit
`Close`, `Stop`, or `Release` methods. Use `defer` where the lifetime matches a
scope.

`runtime.AddCleanup` can attach a last-resort cleanup to an object. Cleanups:

- may run arbitrarily late or not before process exit;
- run concurrently and without ordering guarantees;
- must not receive an argument or closure that keeps the owner reachable;
- may require `runtime.KeepAlive(owner)` after the last operation that needs
  the owner alive;
- are not guaranteed for some tiny, zero-sized, or linker-allocated objects.

`runtime.SetFinalizer` is harder to reason about: it resurrects the object for
another cycle, finalizers execute sequentially, and cycles or dependencies can
prevent expected execution. Prefer `AddCleanup` for new fallback logic, but
neither API is deterministic resource management.

**Use cleanup when:** wrapping a non-Go resource needs a leak safety net in a
long-running process and explicit close remains the primary path. **Backfires
when:** correctness, flushing, lock release, bounded resource usage, or process
shutdown depends on it; registering cleanup on every tiny object can also add
tracking and scheduling cost.
