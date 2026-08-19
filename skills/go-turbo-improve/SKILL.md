---
name: go-turbo-improve
description: Apply a Go performance fix and prove it with benchstat.
argument-hint: "[path, function, or finding]"
disable-model-invocation: true
---

# go-turbo-improve

Apply the fix, keep the behavior, prove the win.

Two things are easy to ship accidentally when someone says "just make it
faster": an optimization that changes behavior is a bug, and an optimization
without a measurement is a guess. The procedure exists to catch both.

## Procedure

Copy this checklist into your response and tick items as you complete them. Each
unticked box is a way to ship a performance claim you cannot defend:

```
Fix progress:
- [ ] Step 1: Diagnosis in hand (which path, which rung)
- [ ] Step 2: Baseline captured to old.txt, tests green
- [ ] Step 3: One coherent change at the highest applicable rung
- [ ] Step 4: Behavior verified (go test, -race if concurrent, go vet)
- [ ] Step 5: new.txt captured, benchstat run
- [ ] Step 6: Reported the number, reverted unmeasurable complexity
```

**1. Know what you're fixing.** Work from an existing diagnosis — from
`$go-turbo-analyze`, a profile, or the user. Without one, spend the first step
finding the bottleneck; optimizing the wrong function is pure cost.

**2. Baseline first.** Before touching anything:

```sh
go test ./...
go test -bench='BenchmarkTarget$' -benchmem -count=10 -run='^$' ./pkg > old.txt
```

Where no suitable measurement exists, add the smallest one that answers the
question: a focused benchmark for local code, or a trace/load test for a
queueing, network, or system effect. A microbenchmark is one valid form of
evidence, and it supports only a microbenchmark claim.

**3. Fix the highest rung that applies.** Work down the ladder in
`skills/go-turbo/SKILL.md`. A fix found high on the ladder usually makes the ones
below it unnecessary.

**4. One change per measurement.** Bundling three optimizations and measuring
once tells you the bundle helped. It does not tell you all three did, and in
practice one is often a regression hidden by the other two.

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

**7. Report the number, whatever it says.** Where the comparison cannot
distinguish a benefit, revert complexity introduced solely for speed. A simple
behavior-preserving cleanup or algorithmic correction may stay for
non-performance reasons, stated as such.

## Rules

- **Behavior is frozen.** Same outputs, same errors, same edge cases, same API.
  Behavior changes are a separate conversation with the user, not something to
  slip into a perf commit.
- **Baseline improvements need established preconditions.** Capacity must be
  defensible; buffering needs flush/error behavior; field layout may be
  externally observable; reuse needs an ownership contract. Apply the simple
  change once those conditions are clear.
- **Paid wins need evidence and a comment.** `sync.Pool`, zero-copy sharing,
  lock-free structures, `unsafe`, GC tuning — each ships with the representative
  measurement and the `turbo:` comment specified in `skills/go-turbo/SKILL.md`.

- **`-race` is mandatory for concurrency changes.** A data race is not a
  performance tradeoff.
- **Stop when the returns stop.** After the top one or two items, further changes
  usually cost more in readability than they return in speed. Say where you
  stopped and what is next.
- **`unsafe` needs a measured bottleneck**, even at `redline`, plus a portable
  fallback where appropriate, focused tests, and a benchmark on every supported
  architecture. User enthusiasm is not evidence.

## Output

The diff, then:

```
<file>:<line> — <what changed and why it's faster>

benchstat old.txt new.txt
  <the actual output>

behavior: tests pass, race clean
next:     <the next rung, or "diminishing returns from here">
```

Where a change was reverted for being unmeasurable, say so — that stops the next
person trying the same thing.

## Boundaries

Optimizes existing code. Architecture redesigns, new dependencies, and public
API changes need the user's agreement first. For a fresh implementation use
`$go-turbo`; for diagnosis without changes, `$go-turbo-analyze`.

For benchmark hygiene read the relevant sections of
[comparing-benchmarks.md](../go-turbo/references/comparing-benchmarks.md); for pattern detail, use
the routing table in `skills/go-turbo/SKILL.md`. Scoped to the current task.
