# Build and Target Flags

Release flags, target selection, and what each one changes about the binary you
ship.

## Release and target flags

Common release choices:

```sh
go build -trimpath -o app ./cmd/app
go build -trimpath -ldflags='-s -w' -o app-small ./cmd/app
go build -gcflags='all=-N -l' -o app-debug ./cmd/app
```

- `-trimpath` removes local source prefixes and improves reproducibility. It is
  not a runtime speed optimization.
- linker `-s -w` removes the linker symbol table and DWARF, reducing binary
  size. Go runtime panic traces retain their own function/line tables, while
  external debugging and some native profiling workflows lose information.
  Validate the observability trade before adopting it.
- `all=-N -l` disables optimization and inlining for debugging. Never use that
  binary for performance comparison.

Injecting version data is a packaging concern:

```sh
go build -ldflags='-X main.version=v1.2.3' -o app ./cmd/app
```

Prefer a build system that passes already-resolved, properly escaped values.
Do not embed shell substitutions in documentation or automation that may handle
untrusted tags.

Cross-compile with explicit target variables:

```sh
GOOS=linux GOARCH=arm64 go build -o app-linux-arm64 ./cmd/app
GOOS=linux GOARCH=amd64 GOAMD64=v3 go build -o app-linux-v3 ./cmd/app
```

A higher architecture baseline may enable faster instructions and may also make
the binary fail on older CPUs. Ship separate artifacts or keep the lowest
supported baseline; benchmark the real workload on each target.

## Build tags and implementations

Use build constraints for a portable implementation plus a platform-specific
fast path:

```go
//go:build linux && amd64

package fastpath
```

Keep identical behavioral tests for every implementation. Add a pure-Go or
portable fallback, and make CI compile all supported tags/targets. Build tags
can remove instrumentation overhead entirely, but they also multiply the test
matrix and can conceal drift.

Prefer standard-library architecture dispatch over home-grown assembly. It
already selects optimized implementations for crypto, hashing, byte search, and
other primitives on supported CPUs.

## Version compatibility

PGO is supported starting in Go 1.20, and compiler diagnostics, experiment
names, target feature variables, and generated instructions change across
releases. Use only flags documented by every supported build toolchain, or
version the build path explicitly with identical behavior tests. Do not raise
the module's minimum Go version or architecture baseline as an incidental
side effect of a performance experiment.
