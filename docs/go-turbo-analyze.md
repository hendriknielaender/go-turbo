# go-turbo-analyze

## What it does

`go-turbo-analyze` answers one question — why is this slow — and hands back a
ranked list of causes with the evidence behind each one, what fixing it would
cost, and how confident the answer is.

It does not touch the code. That constraint is what makes it safe to point at an
unfamiliar repository, and it is also what the skill exists to protect: the
failure mode it was written against is confident guessing, the agent proposing
`sync.Pool` for what turns out to be an O(n²) loop. Findings are ranked by
evidence strength, and anything reached by reading code rather than measuring it
is labelled `code reading only`. Finding nothing is a real result it will
report, rather than filling the page.

## When to reach for it

Type `/go-turbo-analyze` — the agent will not fire it on its own. Pass a path, a
function, or a profile.

Reach for it when something is slow and the cause is genuinely unknown. If you
already know what to fix, skip to [go-turbo-improve](go-turbo-improve.md);
running a diagnosis you do not need is pure cost.

## The output

Each finding carries a tag naming the mechanism — `algo:` for a wrong complexity
class, `alloc:`, `escape:`, `gc:`, `sync:`, `io:`, `net:`, `leak:`, `layout:` —
then the evidence, the share of the problem, the one-line fix, and an effort and
risk rating. `algo:` almost always ranks first, because nothing further down the
ladder rescues an avoidable quadratic.

It closes with a one-sentence verdict and a `measured:` line that either names
the profile it used or tells you what to run to confirm.

Two distinctions do most of the work in the ranking:

| Trap | What it does to a naive reading |
| --- | --- |
| Cumulative vs flat time | A function at 90% cumulative and 2% flat is a caller, not a bottleneck |
| `/allocs` vs `/heap` | Allocation volume is not retained memory; growth needs comparable snapshots over time |

Low CPU with a bad tail is its own signal, and it points away from local compute
— toward queues, external waits, scheduler delay, and lock or channel blocking.

## Common questions

**Why won't it just fix what it found?**

Because read-only scope is the feature. It is one of the repository's behavioral
acceptance cases: given a p99 latency problem and an explicit request to
diagnose rather than fix, an agent that edits files fails the case. Hand the
ranked list to [go-turbo-improve](go-turbo-improve.md) when you have decided
what to act on.

**It said "code reading only" on most findings.**

That is the honest state when no profile was available, and it is deliberately
visible so you can weigh it. Give it a CPU or allocation profile, or a running
service's `/debug/pprof` endpoint, and the same findings come back with measured
shares attached.

## It's working if

- No file in your working tree changed.
- Every finding names its evidence, and unmeasured ones say so.
- The list is ranked by expected impact, not by the order it read the code.
- It descends past high-cumulative callers to the function actually spending the
  time.
- When there is nothing on the hot path, it says so and names what to instrument
  instead.

## Where it fits

The first half of the diagnosis-then-fix chain: `go-turbo-analyze` →
[go-turbo-improve](go-turbo-improve.md), with
[go-turbo-bench](go-turbo-bench.md) supplying evidence when none exists yet. Its
neighbours by scope are [go-turbo-review](go-turbo-review.md) for a diff and
[go-turbo-audit](go-turbo-audit.md) for a whole repository, both of which report
rather than change too. [go-turbo-help](go-turbo-help.md) routes the whole set.
