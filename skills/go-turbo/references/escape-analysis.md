# Reading Escape Analysis

Read what the compiler decided and why, from the full reasoning chain rather
than from a function's name.

## Read the compiler's decision

Inspect the package first; inspect dependencies only when a boundary remains
unexplained:

```sh
go build -gcflags='-m=2' ./path/to/pkg
go test -c -gcflags='-m=2' ./path/to/pkg
go build -gcflags='all=-m=2' ./path/to/pkg
```

The verbose form prints inlining decisions and the data-flow reason for an
escape. Useful messages include:

```text
moved to heap: x
&T{...} escapes to heap
parameter p leaks to ~r0
argument does not escape
inlining call to f
```

`leaks to` describes a relationship between a parameter and a result or
stored location; it does not prove that every call allocates. Likewise, `does
not escape` says nothing about allocations performed elsewhere in the
function. Trace the reasoning chain to the value reported by `allocs/op` or an
allocation profile.

Compiler diagnostics are not a stable API. Wording and placement decisions
can change with Go version, architecture, build tags, instrumentation, PGO,
and surrounding code.

**Use when:** a profile or benchmark identifies a hot allocation and its
source is unclear. **Backfires when:** teams treat every diagnostic as a bug,
or tests assert exact diagnostic text and break on harmless compiler changes.

## Reason about lifetime, not syntax

Taking an address, calling `new`, using a pointer receiver, or converting to
an interface does not inherently allocate. Storage moves to the heap when the
compiler cannot prove that all references die within a safe stack lifetime.

Returning a pointer requires the object to outlive an out-of-line call:

```go
func newConfig() *Config {
	return &Config{}
}
```

That constructor is correct. If it is inlined and the caller does not retain
the result, the compiler may still place the object on the caller's stack.
Judge the call site and shipped binary, not the token `&`.

The compiler also records escape summaries for non-inlined functions. A
pointer argument does not automatically escape merely because the call stayed
out of line.

## Verify the shipped build

After a source-level fix:

1. Build with the production Go version, tags, PGO profile, and architecture.
2. Confirm the intended decision with `-m=2`.
3. Run the focused benchmark with `-benchmem -count=10` and compare with
   `benchstat`.
4. Recheck the allocation profile under representative load.
5. Run correctness tests and `-race` for any ownership or concurrency change.

Race and sanitizer instrumentation can change escape and conversion behavior;
run them for correctness, then measure the production-shaped binary
separately. Keep the optimization only if the number improves and its
ownership rules remain understandable.
