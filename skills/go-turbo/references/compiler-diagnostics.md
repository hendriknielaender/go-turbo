# Reading Compiler Decisions

Establish the build context first — flags and toolchain change the answer — then
read what the compiler reports, including the generated instructions.

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
