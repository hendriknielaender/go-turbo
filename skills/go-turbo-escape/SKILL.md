---
name: go-turbo-escape
description: Audit Go heap escapes: what escapes, why, and which are worth fixing.
argument-hint: "[package or path]"
disable-model-invocation: true
---

# go-turbo-escape

Read what the compiler decided, and fix only the escapes that are accidents of
code shape.

Most escapes are correct. A constructor returning `*T` is idiomatic Go, not a
defect. The value here is separating the escapes worth fixing from the wall of
noise around them — chasing every line of `-m` output is a reliable way to make
code worse.

## Procedure

**1. Collect the diagnostics.**

```sh
go build -gcflags='-m=2' ./... 2>&1 | rg 'escapes to heap|moved to heap'
go build -gcflags='-m=2' ./pkg 2>&1         # with the reasoning chain
go build -gcflags='all=-m=2' ./... 2>&1     # including deps (verbose)
```

**2. Narrow to what matters.** Escape output covers the whole package uniformly;
your hot path does not. Cross-reference with a profile or a benchmark's allocs/op
before reporting. An escape in a startup path is not a finding. Without a
profile, name the functions you assumed were hot and why.

**3. Classify each escape.**

`incidental` — caused by code shape, fixable without changing what the API means:

- a small pointee reported as escaping through a `*T`-returning API when identity
  and nil are not part of the contract and a value result would do
- a `fmt` call boxing arguments into `...any` in a loop
- an allocation inside a loop that could be hoisted and reused
- a closure capturing a variable when a parameter would do
- an interface parameter at a hot internal boundary where the concrete type is
  known

`necessary` — the value genuinely outlives the frame:

- a pointer or reference retained in longer-lived state, a cache, a global, or
  asynchronous work whose lifetime crosses the call
- a local whose address is sent through a channel or captured by a goroutine that
  can outlive the call; sending an ordinary value does not imply the sender's
  local storage escapes
- returned or stored values whose observed caller lifetime requires heap storage
  in the shipped build
- values whose dynamic size or lifetime prevents stack placement

Report a necessary escape only where it is surprising. Explaining why idiomatic
Go is idiomatic is work nobody asked for.

Classify from the compiler's complete reasoning chain and the shipped call sites,
never from a name: escape summaries and inlining can let a returned pointee stay
stack-local at a caller.

**4. Give the restructure.** For each incidental escape, the concrete change:

| Cause | Fix |
|-------|-----|
| Returns a new buffer per call | `AppendX(dst []byte, …) []byte` — caller owns the memory |
| Small pointee escapes through a `*T` result and identity/nil are unnecessary | Return `T` by value and recheck callers |
| `fmt.Sprintf`/`Fprintf` in a hot loop | `strconv.Append*` into a reused buffer, or `WriteString` |
| Allocation inside a loop | Hoist it; `buf = buf[:0]` per iteration |
| Interface param at a hot boundary | Take the concrete type in the internal function |
| Small fixed-size scratch | `var a [64]byte; b := a[:0]` |
| Closure capturing for a callback | Pass the value as a parameter |

**5. Verify with a benchmark, not with `-m`.** `-m` shows what the compiler did;
only allocs/op shows whether it mattered.

```sh
go test -bench='BenchmarkTarget$' -benchmem -count=10 -run='^$' ./pkg > old.txt
# apply
go test -bench='BenchmarkTarget$' -benchmem -count=10 -run='^$' ./pkg > new.txt
benchstat old.txt new.txt
```

## Output

```
<file>:<line> <func> — <what escapes>
  cause:   <the mechanism>
  class:   incidental | necessary
  fix:     <the restructure, or "leave it — this is correct">
```

Then:

```
<N> compiler-reported escapes on the hot path, <M> incidental.
expected mechanism: <which lifetime or allocation should change>
measured: <benchstat result | not run; allocs/op is the only source for it>
```

Nothing worth fixing: `Hot path is escape-clean. The allocations are elsewhere —
check /debug/pprof/allocs.`

## Inlining

Inlining and escape analysis are coupled: an inlined call exposes more of the
callee to the caller's optimization context. A non-inlined call does not by
itself imply escape — the compiler exports escape summaries across many call
boundaries, so read the actual diagnostic.

```sh
go build -gcflags='-m -m' ./pkg 2>&1 | rg 'inline|escape'
```

The inlining cost model and supported constructs change across Go releases. Where
a measured hot path benefits, split a small common path from a larger rare path
and verify the selected toolchain's decision. Report an inlining change only once
benchmark and allocation evidence justify it.

## Rules

- **Keep the code shape the codebase can live with.** Threading a scratch buffer
  through five frames to save a 24-byte allocation off a cold path is a net loss;
  say so when that's the situation.
- **`-m` is not a profile.** It says where allocations come from, never whether
  they matter.
- **Report the exact toolchain used.** Escape and inlining decisions change with
  the compiler, so trust its diagnostics over a remembered release rule.
- **Necessary escapes on cold paths are not findings.**

For the full catalog of causes and restructures, read the relevant sections of
[escape-causes.md](../go-turbo/references/escape-causes.md).

## Boundaries

Escape and inlining only. Allocation that isn't escape-driven — map growth, slice
growth, interface boxing volume — belongs to `$go-turbo-analyze`. Reports and, on
request, applies fixes. Scoped to the current task.
