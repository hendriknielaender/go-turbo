---
name: go-turbo-improve
description: >
  Apply performance fixes to existing Go code and prove they worked. Takes a
  diagnosis (from /go-turbo-analyze, a profile, or the user's own finding),
  makes the smallest change that addresses it, and benchmarks before and
  after with benchstat. Use when the user says "make this faster", "optimize
  this", "reduce the allocations here", "fix this bottleneck", "speed up this
  function", "apply the fix", "/go-turbo-improve", or hands over a slow
  function and asks for a faster version. Preserves behavior exactly —
  optimization, not redesign.
license: MIT
---

# go-turbo-improve

Apply the fix, keep the behavior, prove the win. This is the execution half
of `/go-turbo-analyze`.

The discipline that makes this skill trustworthy: an optimization that
changes behavior is a bug, and an optimization without a measurement is a
guess. Both are easy to ship accidentally when someone says "just make it
faster."

## Procedure

**1. Know what you're fixing.** If a diagnosis exists — from
`/go-turbo-analyze`, a profile, or the user — work from it. If not, spend the
first step finding the bottleneck rather than optimizing the first thing you
see. Optimizing the wrong function is pure cost.

**2. Baseline first.** Before touching anything:

```sh
go test ./... > /dev/null                                     # green?
go test -bench=<target> -benchmem -count=10 -run=^$ ./pkg > old.txt
```

If no benchmark exists, write one for the target function first. It is the
only way to know afterward whether you helped, and it stays in the repo as a
regression guard. A benchmark you skip is a change you can't defend.

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
go test -bench=<target> -benchmem -count=10 -run=^$ ./pkg > new.txt
benchstat old.txt new.txt
```

**7. Report the number, whatever it says.** If `benchstat` shows `~` or
`p ≥ 0.05`, the change did not measurably help — revert it. Shipping added
complexity for an unmeasurable win is exactly what this skill exists to
prevent, and reverting is the professional outcome, not a failure.

## Rules

- **Behavior is frozen.** Same outputs, same errors, same edge cases, same
  API. Behavior changes are a separate conversation with the user, not
  something to slip into a perf commit.
- **Free wins need no permission.** Preallocation with known size,
  `strings.Builder`, buffered I/O, field reordering, hoisted allocations —
  apply them and move on.
- **Paid wins need evidence and a comment.** `sync.Pool`, zero-copy sharing,
  lock-free structures, `unsafe`, GC tuning. Each ships with a benchmark and
  a `turbo:` comment naming what was traded:

```go
// turbo: pooled decode buffers; the returned slice aliases the pool buffer
// and is invalid after the next Decode. Drop the pool if allocation stops
// showing in profiles.
```

- **`-race` is not optional** for concurrency changes. A data race is not a
  performance tradeoff.
- **Stop when the returns stop.** After the top one or two items, further
  changes usually cost more in readability than they return in speed. Say
  where you stopped and what's next, rather than grinding through diminishing
  returns.
- **Don't reach for `unsafe` unless the user asked or the level is
  `redline`.** And then only with a benchmark in the same response.

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
`/go-turbo` directly; for diagnosis without changes, `/go-turbo-analyze`.

Load the relevant `references/*.md` from the `go-turbo` skill for the pattern
being applied, and `references/measurement.md` for benchmark hygiene.

"stop go-turbo-improve" or "normal mode" to revert.
