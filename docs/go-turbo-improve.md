# go-turbo-improve

## What it does

`go-turbo-improve` applies one performance fix, keeps the behaviour identical,
and proves the result with `benchstat`.

It captures the baseline before it touches anything. That ordering is the skill:
a measurement taken after the change has nothing to compare against, and an
optimisation without a comparison is a guess wearing a diff. It makes one
coherent change per measurement, because bundling three optimisations and
measuring once tells you the bundle helped while hiding that one of them was a
regression. When the comparison cannot distinguish a benefit, it reverts the
complexity it added and says so.

## When to reach for it

Type `/go-turbo-improve` — the agent will not fire it on its own. Pass a path, a
function, or a finding from [go-turbo-analyze](go-turbo-analyze.md).

Reach for it when you know what to fix. Without a diagnosis it will spend its
first step finding one, which is [go-turbo-analyze](go-turbo-analyze.md)'s job
done less well.

## Behaviour is frozen

Same outputs, same errors, same edge cases, same API. A behaviour change is a
separate conversation with you, not something that rides along in a performance
commit — and `-race` is mandatory when anything concurrent moved, because a data
race is not a performance tradeoff.

For non-trivial logic changes it will differential-test the new implementation
against the old rather than trusting the existing suite to have covered the
edge it just moved.

The checklist it works through is visible in its response, which is the point:
each unticked box is a way to ship a claim you cannot defend.

## Common questions

**It reverted my optimisation.**

Then `benchstat` could not distinguish it from the baseline. A statistically
indistinguishable result is no measured change, and complexity added purely for
speed does not survive that. If the change is worth keeping for another reason —
it is simpler, or it fixes an algorithmic wart — say so and it stays, labelled as
such rather than as a performance win.

**Why ten runs? One benchmark took long enough.**

One run is a sample of size one, and `ns/op` drifts with machine load. `-count=10`
is what makes the comparison a comparison rather than two anecdotes.

## It's working if

- `old.txt` exists before the diff does.
- The response contains actual `benchstat` output, not a percentage.
- One mechanism changed per measurement.
- `go test -race` ran whenever concurrency moved.
- It tells you where it stopped and what the next rung would be.
- Something it tried and could not measure was removed again, and mentioned.

## Where it fits

The execution half of the chain: [go-turbo-analyze](go-turbo-analyze.md) →
`go-turbo-improve`. It optimises code that exists — architecture redesigns, new
dependencies, and public API changes need your agreement first, and a fresh
implementation belongs to [go-turbo](go-turbo.md). For benchmark hygiene beneath
it, see [go-turbo-bench](go-turbo-bench.md);
[go-turbo-help](go-turbo-help.md) routes the whole set.
