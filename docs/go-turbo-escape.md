# go-turbo-escape

## What it does

`go-turbo-escape` runs the compiler's escape diagnostics, maps each escape to
its cause, and tells you which ones are worth fixing.

Most escapes are correct, and that is the fact the skill is built around. A
constructor returning `*T` is idiomatic Go, not a defect; chasing every line of
`-gcflags=-m` output is a reliable way to make code worse. The value here is the
separation — `incidental` escapes that come from code shape and can be
restructured, against `necessary` ones where the value genuinely outlives the
frame. It reports a necessary escape only where it is surprising, because
explaining why idiomatic Go is idiomatic is work nobody asked for.

## When to reach for it

Type `/go-turbo-escape` — the agent will not fire it on its own. Pass a package
or a path.

Reach for it when allocation is the known problem and you want to know which of
it the compiler could avoid. Allocation that is not escape-driven — map growth,
slice growth, interface boxing volume — belongs to
[go-turbo-analyze](go-turbo-analyze.md) instead.

## `-m` is not a profile

The diagnostics say where allocations come from. They never say whether those
allocations matter. Escape output covers a package uniformly; your hot path does
not, so the skill cross-references a profile or a benchmark's `allocs/op` before
reporting, and where no profile exists it names the functions it assumed were hot
and why. An escape in a startup path is not a finding.

The verification rule follows from the same idea: `-m` shows what the compiler
did, and only `allocs/op` shows whether it mattered. A fix is not done until a
benchmark moves.

Classification comes from the compiler's full reasoning chain and the real call
sites, never from a function's name — escape summaries and inlining can let a
returned pointee stay stack-local at a caller.

## Common questions

**It told me to leave most of the escapes alone.**

That is the expected outcome on idiomatic code. The skill is a filter, not a
campaign: if the hot path is escape-clean it will say so and point you at
`/debug/pprof/allocs` for where the allocations actually are.

**Threading a buffer through five functions saved one allocation. Worth it?**

The skill's own answer is usually no, and it will say so — a code shape the
codebase cannot live with is a net loss against a 24-byte allocation off a cold
path. That judgment is part of the report rather than left to you.

## It's working if

- Each escape is classified `incidental` or `necessary`, with the mechanism named.
- Necessary escapes on cold paths do not appear as findings.
- Every incidental escape comes with a concrete restructure, not a principle.
- The report names the exact toolchain, since escape and inlining decisions move
  between releases.
- The fix is verified with `allocs/op`, not with a second reading of `-m`.

## Where it fits

A focused standalone for one rung of [go-turbo](go-turbo.md)'s ladder — rung
four, incidental escapes, which sits below algorithm and allocation work and
above boundary amortisation. Reach for it after
[go-turbo-analyze](go-turbo-analyze.md) has pointed at allocation, and use
[go-turbo-bench](go-turbo-bench.md) for the measurement that confirms a fix.
[go-turbo-help](go-turbo-help.md) routes the whole set.
