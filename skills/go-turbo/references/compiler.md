# Compiler and Build

Let the compiler perform ordinary optimization. Use diagnostics to learn what
it proved, then reshape code only when a measured hot path needs help. Compiler
output explains mechanism; it does not establish impact.

## Contents

- [Establish the build context](#establish-the-build-context)
- [Inspect compiler decisions](#inspect-compiler-decisions)
- [Inlining and devirtualization](#inlining-and-devirtualization)
- [Bounds-check elimination](#bounds-check-elimination)
- [Profile-guided optimization](#profile-guided-optimization)
- [Release and target flags](#release-and-target-flags)
- [Build tags and implementations](#build-tags-and-implementations)
- [cgo and static builds](#cgo-and-static-builds)
- [Experiments and low-level code](#experiments-and-low-level-code)
- [Inspect generated instructions](#inspect-generated-instructions)
- [Version compatibility](#version-compatibility)

## Establish the build context

Before interpreting a diagnostic, capture the compiler and target:

```sh
go version
go env GOOS GOARCH GOAMD64 GOARM64 CGO_ENABLED GOEXPERIMENT
go list -m -f '{{.GoVersion}}' 2>/dev/null || true
```

The module's `go` directive controls language and standard-library assumptions;
the installed toolchain controls optimization. Re-run diagnostics and
benchmarks on the deployment toolchain and architecture. A compiler decision
from another release is not durable evidence.

Use normal optimized builds for performance measurements. `-race`, coverage,
debug flags, and some sanitizers intentionally change code generation and
runtime behavior.

## Inspect compiler decisions

```sh
go build -gcflags='-m' ./...          # escape and inlining summaries
go build -gcflags='-m -m' ./pkg       # more explanation
go build -gcflags='all=-m' ./cmd/app  # include dependencies; very verbose
```

Use a package pattern intentionally. `all=` changes which packages receive the
flags; it is not required for ordinary diagnostics in the package being edited.

For bounds checks that remain:

```sh
go build -gcflags='-d=ssa/check_bce/debug=1' ./pkg
```

Diagnostics can change after an unrelated edit because inlining and escape
analysis interact. Confirm the outcome with `B/op` and `allocs/op`; do not count
diagnostic lines as saved allocations.

## Inlining and devirtualization

Inlining removes a call boundary and exposes more code to constant propagation,
escape analysis, and bounds-check elimination. The compiler uses a cost model
that changes between releases. Avoid memorizing a fixed budget or a permanent
list of blockers.

```sh
go build -gcflags='-m -m' ./pkg 2>&1 | rg 'inline|devirtual'
```

Non-inlined calls do not imply that pointer arguments escape. The compiler
exports escape summaries across many call boundaries. Read the actual escape
diagnostic.

Interface calls and function values inhibit ordinary direct-call inlining, but
the compiler can sometimes devirtualize when it proves the concrete target;
PGO can provide additional hot-call evidence. Check the selected toolchain's
output instead of assuming either outcome.

When a measured function is too large to inline, keep a small common path and
move rare work behind a helper:

```go
func (c *Cache) Get(key string) (Value, bool) {
	if value, ok := c.hot[key]; ok {
		return value, true
	}
	return c.getSlow(key)
}
```

Use this shape only when it remains clear and a benchmark shows a benefit.
Splitting code can add branches, duplicate checks, and worsen instruction-cache
behavior.

`//go:noinline` is useful for controlled compiler experiments. It is rarely a
production optimization and should not be left behind without measured need.

## Bounds-check elimination

The compiler normally eliminates checks in canonical loops:

```go
func sum(values []int) int {
	total := 0
	for i := 0; i < len(values); i++ {
		total += values[i]
	}
	return total
}
```

`range` is equally natural when the index is not needed. Choose the clearer
form and inspect BCE output only for a measured tight loop.

When several fixed offsets are accessed, one explicit proof can dominate later
checks:

```go
func decodeHeader(data []byte) (uint32, uint32) {
	_ = data[7]
	return binary.BigEndian.Uint32(data[:4]),
		binary.BigEndian.Uint32(data[4:8])
}
```

This preserves the same panic boundary while making the required length clear.
At trust boundaries, prefer an explicit length error rather than relying on a
panic:

```go
func decodeHeader(data []byte) (uint32, uint32, error) {
	if len(data) < 8 {
		return 0, 0, io.ErrUnexpectedEOF
	}
	return binary.BigEndian.Uint32(data[:4]),
		binary.BigEndian.Uint32(data[4:8]), nil
}
```

Loops indexing two independent slices often retain a check for the second
slice. Validate lengths once before the loop when the API requires them to
match. Never remove validation merely to remove a bounds check.

The payoff is usually tiny outside parsing, crypto, compression, numeric, and
codec loops. Require a benchmark before making code less direct.

## Profile-guided optimization

PGO lets the compiler use a CPU profile to prioritize hot call edges and make
more aggressive inlining/devirtualization choices. It is a low-code-change
option, not a reason to skip application profiling.

Place a representative profile named `default.pgo` in the main package
directory, or pass a profile explicitly:

```sh
go build -pgo=./profiles/service.pprof -o service ./cmd/service
go build -pgo=off -o service-nopgo ./cmd/service
```

Compare PGO on and off with the workload and binary that matter. Keep these
rules:

- collect from a representative mix, not a single synthetic endpoint;
- do not publish profiles containing sensitive symbol or path information
  without review;
- retain the exact profile used for reproducible release builds;
- refresh it when call paths or workloads change materially;
- verify binary size, startup, CPU, and tail latency rather than assuming every
  metric improves;
- test each target architecture separately.

A stale profile is usually tolerated, but “usually” is not an acceptance test.

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

## cgo and static builds

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

## Experiments and low-level code

Record active experiments and inspect the selected compiler instead of copying
flags from another release. Consult that toolchain's release notes and source
for the supported experiment names:

```sh
go env GOEXPERIMENT
go tool compile -help
```

Compiler experiments, runtime experiments, `unsafe`, SIMD packages, and
assembly are evidence-gated. For each:

- keep a correct portable baseline;
- benchmark representative sizes and architectures;
- run differential/property/fuzz tests;
- run the race detector where supported;
- document alignment, aliasing, CPU-feature, and lifetime assumptions;
- provide a removal trigger and a fallback for unsupported toolchains.

Do not use `unsafe.String` or `unsafe.Slice` merely to remove a conversion. The
resulting alias and lifetime contract is often more expensive than the copy and
can turn immutable strings into mutable shared state.

## Inspect generated instructions

Use assembly only after a profile and benchmark identify a small important
function:

```sh
go build -gcflags='-S' ./pkg 2> assembly.txt
go tool objdump -s 'example\.com/project/pkg\.Function' ./app
```

Answer a specific question: whether a bounds check remains, which instruction
implements an atomic, whether hardware crypto dispatch occurred, or why a loop
did not compile as expected. Do not optimize by visual preference for shorter
assembly; measure the resulting binary on supported hardware.

## Version compatibility

PGO is supported starting in Go 1.20, and compiler diagnostics, experiment
names, target feature variables, and generated instructions change across
releases. Use only flags documented by every supported build toolchain, or
version the build path explicitly with identical behavior tests. Do not raise
the module's minimum Go version or architecture baseline as an incidental
side effect of a performance experiment.
