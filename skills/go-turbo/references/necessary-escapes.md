# Necessary Escapes

Most escapes are correct. Report one only where it is surprising — explaining
why idiomatic Go is idiomatic is work nobody asked for.

Keep heap allocation when any of these is true:

- The object genuinely outlives the call: cache entry, shared state,
  asynchronous message, or returned mutable identity.
- A constructor runs rarely and pointer semantics make the API clearer.
- Avoiding the escape requires pervasive scratch parameters, unsafe aliases,
  or an object pool without measured benefit.
- A large object is safer and cheaper on the heap than in many growing or
  recursive stacks.
- The allocation is absent from representative profiles.

`sync.Pool` does not make an object stack allocated; it amortizes heap objects
and adds a lifetime protocol. Use it only under the conditions in `pooling.md`.

For finalizers, cleanups, cgo handles, or syscalls that use a resource after
the compiler's last visible reference, place `runtime.KeepAlive` after the
last operation that requires the owner. Do not use `KeepAlive` to conceal an
ordinary ownership error.
