---
name: go-turbo-escape
description: >
  Heap escape audit for Go. Runs go build -gcflags=-m, maps every escape to
  its cause, separates the incidental ones (fixable by code shape) from the
  necessary ones (the value really does outlive the frame), and gives the
  restructure for each fixable one. Use when the user says "escape analysis",
  "why is this allocating", "what's escaping to the heap", "gcflags -m",
  "moved to heap", "keep this on the stack", "reduce heap allocations",
  "/go-turbo-escape", or shows -m output and asks what it means.
license: MIT
---

# go-turbo-escape

Read what the compiler decided, and fix only the escapes that are accidents
of code shape.

Most escapes are correct. A constructor returning `*T` is idiomatic Go, not a
defect. The value of this skill is in separating the escapes worth fixing
from the wall of noise around them — chasing every line of `-m` output is a
reliable way to make code worse.

## Procedure

**1. Collect the diagnostics.**

```sh
go build -gcflags=-m ./... 2>&1 | grep -E 'escapes to heap|moved to heap'
go build -gcflags='-m -m' ./pkg 2>&1        # with the reasoning chain
go build -gcflags=all=-m ./... 2>&1         # including deps (verbose)
```

**2. Narrow to what matters.** Escape output covers the whole package
uniformly; your hot path does not. Cross-reference with a profile or a
benchmark's allocs/op before reporting. An escape in a startup path is not a
finding. If no profile exists, say which functions you assumed were hot and
why.

**3. Classify each escape.**

`incidental` — caused by code shape, fixable without changing what the API
means:
- returning `*T` for a small struct that could be returned by value
- a `fmt` call boxing arguments into `...any` in a loop
- an allocation inside a loop that could be hoisted and reused
- a closure capturing a variable when a parameter would do
- an interface parameter at a hot internal boundary where the concrete type
  is known

`necessary` — the value genuinely outlives the frame:
- constructors, factories, anything stored in a struct or global
- values sent on channels or captured by goroutines
- anything put in a cache or returned into caller-owned state
- runtime-sized allocations too large for the frame

Report necessary escapes only if they're surprising — do not generate work
that consists of explaining why idiomatic Go is idiomatic.

**4. Give the restructure.** For each incidental escape, the concrete change:

| Cause | Fix |
|-------|-----|
| Returns a new buffer per call | `AppendX(dst []byte, …) []byte` — caller owns the memory |
| Returns `*T` for a small struct | Return `T` by value |
| `fmt.Sprintf`/`Fprintf` in a hot loop | `strconv.Append*` into a reused buffer, or `WriteString` |
| Allocation inside a loop | Hoist it; `buf = buf[:0]` per iteration |
| Interface param at a hot boundary | Take the concrete type in the internal function |
| Small fixed-size scratch | `var a [64]byte; b := a[:0]` |
| Closure capturing for a callback | Pass the value as a parameter |

**5. Verify with a benchmark, not with `-m`.** `-m` shows what the compiler
did; only allocs/op shows whether it mattered.

```sh
go test -bench=<target> -benchmem -count=10 -run=^$ ./pkg > old.txt
# apply
go test -bench=<target> -benchmem -count=10 -run=^$ ./pkg > new.txt
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
<N> escapes on the hot path, <M> incidental.
projected: -<K> allocs/op   measured: <benchstat result | not yet run>
```

Nothing worth fixing: `Hot path is escape-clean. The allocations are
elsewhere — check /debug/pprof/allocs.`

## Inlining

Inlining and escape analysis are coupled: an inlined call lets the compiler
see the callee's use of an argument and often prove it doesn't escape. When
a call isn't inlined, pointer arguments are assumed to escape.

```sh
go build -gcflags='-m -m' ./pkg 2>&1 | grep 'cannot inline'
```

Blockers: `defer`, `select`, `go`, `range` over a channel, recursion, calls
through an interface or function value, or simply exceeding the ~80-node
budget. The fix, when it's worth it, is splitting a hot function into a small
inlinable fast path and a larger slow path. Report an inlining blocker only
when it's causing an escape you'd otherwise fix.

## Rules

- **Don't contort code to defeat escape analysis.** Threading a scratch
  buffer through five frames to save a 24-byte allocation off a cold path is
  a net loss. Say so when that's the situation.
- **`-m` is not a profile.** It says where allocations come from, never
  whether they matter.
- **Note Go version effects.** Go 1.26 stack-allocates slice backing stores
  in more cases than earlier releases; an escape present on an older
  toolchain may already be gone. Say which version you ran.
- **Necessary escapes on cold paths are not findings.**

Load `references/escape-analysis.md` from the `go-turbo` skill for the full
catalog of causes and restructures.

## Boundaries

Escape and inlining only. Allocation that isn't escape-driven (map growth,
slice growth, interface boxing volume) belongs to `/go-turbo-analyze`.
Reports and, on request, applies fixes.

"stop go-turbo-escape" or "normal mode" to revert.
