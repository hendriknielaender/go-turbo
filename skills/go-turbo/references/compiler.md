# Compiler and Build

Go deliberately exposes far fewer knobs than C++ or Rust. The compiler
already inlines, eliminates dead code, removes redundant bounds checks, and
decides stack vs heap placement. The value here is mostly in *seeing* what it
did, not in overriding it — plus two build-level features that pay for
themselves: PGO and stripped release builds.

## Contents

- [Seeing the compiler's decisions](#seeing-the-compilers-decisions)
- [Inlining](#inlining)
- [Bounds check elimination](#bounds-check-elimination)
- [Profile-guided optimization](#profile-guided-optimization)
- [Build and link flags](#build-and-link-flags)
- [Build tags](#build-tags)
- [Static binaries and cgo](#static-binaries-and-cgo)
- [Runtime GOEXPERIMENT flags](#runtime-goexperiment-flags)
- [Disassembly](#disassembly)

## Seeing the compiler's decisions

```sh
go build -gcflags=-m ./...            # escape + inlining
go build -gcflags='-m -m' ./...       # with reasoning
go build -gcflags=-m=2 ./...          # same, alternate spelling
go build -gcflags=all=-m ./... 2>&1   # including dependencies (verbose)
```

Escape output is covered in `references/escape-analysis.md`. The other two
worth knowing:

```sh
# Bounds checks the compiler could NOT eliminate:
go build -gcflags='-d=ssa/check_bce/debug=1' ./pkg

# Why a specific function wasn't inlined:
go build -gcflags='-m -m' ./pkg 2>&1 | grep 'cannot inline'
```

`-gcflags` applies to the packages you name unless you prefix with `all=`.

## Inlining

Inlining removes call overhead and, more importantly, lets escape analysis
see through the call — which is often where the real win comes from (an
argument that would otherwise be assumed to escape can be proven not to).

The budget is roughly 80 AST nodes. Things that block inlining outright:

- `defer`
- `select`
- `go` statements
- `range` over a channel
- recursion
- calls through an interface or function value (the call site itself can't
  be devirtualized)
- `recover`

Mid-stack inlining means a function containing calls can still be inlined, as
long as the whole thing fits the budget.

The productive pattern is a small inlinable fast path delegating to a larger
slow path — the shape the standard library uses throughout:

```go
func (b *Buffer) WriteByte(c byte) error {
    if b.n < len(b.buf) {          // inlines
        b.buf[b.n] = c
        b.n++
        return nil
    }
    return b.grow(c)               // rare, doesn't need to inline
}
```

`//go:noinline` forces the opposite and is mainly a benchmarking tool: put it
on a function to stop the compiler from inlining and then eliminating the
work you're trying to measure.

Don't chase inlining generally. Chase it when a profile shows call overhead
in something invoked millions of times, and verify with `benchstat` — `-m`
tells you what the compiler did, not whether it helped.

## Bounds check elimination

Every slice index is bounds-checked unless the compiler can prove it safe. It
usually can, but you can help it — and unlike most micro-optimizations, the
helpful forms are also the more readable ones.

```go
// The compiler must check on each access.
func sum(s []int) int {
    total := 0
    for i := 0; i < len(s); i++ {
        total += s[i]
    }
    return total
}

// range: the index is provably in bounds.
func sum(s []int) int {
    total := 0
    for _, v := range s {
        total += v
    }
    return total
}
```

For multiple fixed offsets, one hint up front lets the compiler drop the rest:

```go
func parseHeader(b []byte) (uint32, uint32) {
    _ = b[7]                                   // one check, panics early
    return binary.BigEndian.Uint32(b[0:4]),
           binary.BigEndian.Uint32(b[4:8])     // both now provably safe
}
```

Verify rather than assume:

```sh
go build -gcflags='-d=ssa/check_bce/debug=1' ./pkg
```

The payoff is small in absolute terms. It matters in genuinely tight numeric
loops and nowhere else.

## Profile-guided optimization

PGO (Go 1.21+, stable and on by default when a profile is present) is the
highest-value compiler feature in this file, and it requires almost nothing
from you.

Drop a CPU profile named `default.pgo` next to `main` and `go build` picks it
up automatically:

```sh
curl -o default.pgo 'http://prod-host:6060/debug/pprof/profile?seconds=60'
go build ./cmd/service      # PGO applied automatically
```

With it, the compiler inlines more aggressively along hot paths and
devirtualizes interface calls whose concrete type dominates in the profile.
Typical reported gains are in the low single-digit percent range — 2–7% on
real services — for a change that is a file in a directory.

Practical notes:

- The profile must come from a **representative production workload**. A
  profile from a synthetic benchmark optimizes for the benchmark.
- Profiles age. Refresh when the hot path changes materially; a stale profile
  is mildly harmful, not catastrophic.
- Commit `default.pgo` so builds are reproducible.
- Verify with `benchstat` like any other change.

## Build and link flags

```sh
# Release: strip symbol table and DWARF. Typically 20-30% smaller binary.
go build -ldflags="-s -w" -o app ./cmd/app

# Inject version metadata without touching source.
go build -ldflags="-s -w -X main.version=$(git describe --tags)" -o app

# Debugging: disable optimization and inlining so the debugger tracks source.
go build -gcflags="all=-N -l" -o app-debug ./cmd/app

# Reproducible paths.
go build -trimpath -o app ./cmd/app
```

`-s -w` reduces size only; it does not make the program faster. It does make
stack traces less useful — symbol names survive but line detail degrades —
so weigh it against your debugging story. `-trimpath` removes local
filesystem paths, which is good hygiene for reproducible builds.

Cross-compiling is environment variables, no toolchain install:

```sh
GOOS=linux GOARCH=arm64 go build -o app-arm64 ./cmd/app
```

`GOAMD64=v3` targets a newer amd64 baseline (AVX2 etc.), which can help
numeric code — at the cost of not running on older CPUs. Measure before
adopting; the gain is workload-specific and often zero.

## Build tags

Conditional compilation for platform-specific fast paths:

```go
//go:build linux && amd64

package fastpath
```

```sh
go build -tags=debug ./...
```

Useful for keeping an optimized platform-specific implementation alongside a
portable fallback, and for compiling out expensive instrumentation entirely
rather than branching on a flag at runtime.

## Static binaries and cgo

`CGO_ENABLED=0` produces a fully static binary using the pure-Go DNS resolver
— ideal for `scratch` and `distroless` containers, and it removes a class of
glibc-version deployment problems:

```sh
CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o app ./cmd/app
```

When you genuinely need cgo, static linking takes more:

```sh
CGO_ENABLED=1 GOOS=linux CC=gcc \
  go build -tags netgo \
  -ldflags="-linkmode=external -extldflags '-static'" -o app ./cmd/app
```

`netgo` forces the pure-Go resolver even with cgo enabled, avoiding a runtime
dependency on `getaddrinfo`. Static linking needs `.a` versions of every C
library you link, which not all distributions ship.

On performance: each cgo call has real overhead — it switches to a system
stack and blocks the goroutine's M for the duration. Go 1.26 cut the baseline
overhead by roughly 30%, but the shape of the advice is unchanged: cgo in a
hot loop is a bottleneck. Batch across the boundary, or find a pure-Go
alternative. And a cgo call that blocks holds an OS thread, so high
concurrency over cgo grows the thread count.

## Runtime GOEXPERIMENT flags

Set at build time, these toggle runtime features:

```sh
GOEXPERIMENT=nogreenteagc go build ./...        # opt out of the Go 1.26 GC
GOEXPERIMENT=goroutineleakprofile go build ./... # experimental leak profile
GOEXPERIMENT=simd go build ./...                 # experimental SIMD package
```

The Green Tea collector is the default in Go 1.26 and the opt-out is expected
to disappear in 1.27 — use it to A/B a regression, not as a permanent
setting. The goroutine leak profile is genuinely useful for hunting the leaks
described in `references/concurrency.md`. The `simd`/`archsimd` package is
amd64-only, explicitly unstable, and not portable; treat it as a research
tool rather than something to ship.

## Disassembly

When you need to see the actual instructions:

```sh
go build -gcflags=-S ./pkg 2>&1 | less
go tool objdump -s 'pkg\.Function' ./binary
```

Rarely necessary. It answers questions like "did the compiler vectorize
this," "is this bounds check actually gone," and "did this call get inlined"
definitively when `-m` output is ambiguous. Reach for it after a benchmark
has already told you the function matters — never as a first step.
