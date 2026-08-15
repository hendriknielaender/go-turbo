---
name: go-turbo-improve
description: >
  Apply performance fixes to existing Go code and prove they worked. Takes a
  diagnosis (from $go-turbo-analyze, a profile, or the user's own finding),
  makes the smallest change that addresses it, and benchmarks before and
  after with benchstat. Use when the user says "make this faster", "optimize
  this", "reduce the allocations here", "fix this bottleneck", "speed up this
  function", "apply the fix", "$go-turbo-improve", or hands over a slow
  function and asks for a faster version. Preserves behavior exactly —
  optimization, not redesign.
---

# go-turbo-improve

Apply the fix, keep the behavior, prove the win. This is the execution half
of `$go-turbo-analyze`.

The discipline that makes this skill trustworthy: an optimization that
changes behavior is a bug, and an optimization without a measurement is a
guess. Both are easy to ship accidentally when someone says "just make it
faster."

## Procedure

**1. Know what you're fixing.** If a diagnosis exists — from
`$go-turbo-analyze`, a profile, or the user — work from it. If not, spend the
first step finding the bottleneck rather than optimizing the first thing you
see. Optimizing the wrong function is pure cost.

**2. Baseline first.** Before touching anything:

```sh
go test ./...
go test -bench='BenchmarkTarget$' -benchmem -count=10 -run='^$' ./pkg > old.txt
```

If no suitable measurement exists, add the smallest one that answers the
question: a focused benchmark for local code, or a trace/load test for a
queueing, network, or system effect. A microbenchmark is not the only valid
evidence and must not be used to claim an end-to-end win.

**3. Fix the highest rung that applies.** Work down the go-turbo ladder:
redundant work → algorithm → allocation → escape → boundary crossings →
contention → layout. A fix found high on the ladder usually makes the ones
below it unnecessary.

**4. One change per measurement.** Bundling three optimizations and measuring
once tells you the bundle helped. It does not tell you that all three did,
and in practice one of them is often a regression hidden by the other two.

**5. Verify behavior is unchanged.**

```sh
go test ./...
go test -race ./...          # mandatory if anything concurrent changed
go vet ./...
```

For non-trivial logic changes, a quick fuzz or differential check against the
old implementation is worth the five minutes:

```go
func FuzzSameAsOld(f *testing.F) {
    f.Fuzz(func(t *testing.T, in []byte) {
        if !reflect.DeepEqual(oldParse(in), newParse(in)) {
            t.Fatal("behavior changed")
        }
    })
}
```

**6. Measure and compare.**

```sh
go test -bench='BenchmarkTarget$' -benchmem -count=10 -run='^$' ./pkg > new.txt
benchstat old.txt new.txt
```

**7. Report the number, whatever it says.** If the comparison cannot
distinguish a benefit, revert complexity introduced solely for speed. A
simple behavior-preserving cleanup or algorithmic correction may remain for
non-performance reasons, but do not claim it is faster without evidence.

## Rules

- **Behavior is frozen.** Same outputs, same errors, same edge cases, same
  API. Behavior changes are a separate conversation with the user, not
  something to slip into a perf commit.
- **Baseline improvements need established preconditions.** Capacity must be
  defensible; buffering needs flush/error behavior; field layout may be
  externally observable; reuse needs an ownership contract. Apply the simple
  change when those conditions are clear, and do not invent a speedup.
- **Paid wins need evidence and a comment.** `sync.Pool`, zero-copy sharing,
  lock-free structures, `unsafe`, GC tuning. Each ships with the representative
  measurement and a `turbo:` comment naming what was traded:

```go
// turbo: pools internal decode scratch after BenchmarkDecode removed 1 alloc/op.
// Decode copies caller-owned output; pooled bytes never escape this function.
// Drop the pool if scratch allocation stops appearing in production profiles.
```

- **`-race` is not optional** for concurrency changes. A data race is not a
  performance tradeoff.
- **Stop when the returns stop.** After the top one or two items, further
  changes usually cost more in readability than they return in speed. Say
  where you stopped and what's next, rather than grinding through diminishing
  returns.
- **User interest is not evidence for `unsafe`.** Even at `redline`, require a
  measured bottleneck, a portable fallback when appropriate, focused tests,
  and a benchmark on every supported architecture.

## Output

The diff, then:

```
<file>:<line> — <what changed and why it's faster>

benchstat old.txt new.txt
  <the actual output>

behavior: tests pass, race clean
next:     <the next rung, or "diminishing returns from here">
```

If a change was reverted for being unmeasurable, say so explicitly — that's
useful information, and it stops someone else from trying the same thing.

## Boundaries

Optimizes existing code. Does not redesign architecture, add dependencies
without asking, or change public APIs. For a fresh implementation, use
`$go-turbo` directly; for diagnosis without changes, `$go-turbo-analyze`.

When the core skill is installed alongside this one, use `$go-turbo`'s routing
table for the complete pattern reference and load the
[measurement reference](../go-turbo/references/measurement.md) for benchmark
hygiene. This workflow remains usable without those optional references.
Task-scoped.
