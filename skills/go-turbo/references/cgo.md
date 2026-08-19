# cgo and Static Builds

The call boundary cost and the linking consequences, both of which are support
decisions as much as performance ones.

Crossing between Go and C has fixed overhead, changes scheduler behavior, and
introduces memory the Go runtime cannot fully account for. A cgo call in a hot
per-item loop is a boundary-amortization problem: batch work across it before
attempting low-level call tuning.

Measure both sides of the boundary. C allocation is excluded from Go's memory
limit and ordinary heap profile, so use process metrics and native tools too.
Blocking C calls consume OS threads; bound their concurrency.

For a pure-Go static deployment:

```sh
CGO_ENABLED=0 GOOS=linux go build -trimpath -o app ./cmd/app
```

This changes DNS resolver and cgo-dependent package behavior. Test name
resolution, certificate roots, timezone data, and any dynamically loaded
features in the final container.

External static linking with cgo is platform- and dependency-specific. It needs
static forms of every native library and a complete license/security review; do
not present one linker command as portable.
