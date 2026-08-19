# go-turbo

## What it does

`go-turbo` writes, refactors, reviews, and diagnoses Go with performance in
view — the mode you put an agent in when latency, throughput, allocation, or
memory is part of the requirement rather than an afterthought.

Its defining move is refusing to call anything faster that it has not measured.
An agent asked to optimise Go will reliably reach for `sync.Pool`, `unsafe`, and
pointer-everywhere APIs, because those read as what a performance expert does.
`go-turbo` sorts changes into two classes: ordinary improvements that ship once
their preconditions hold, and paid wins — pooling, zero-copy aliasing, lock-free
structures, GC knobs, `unsafe` — that need a representative profile, benchmark,
or production metric first, and that ship with a comment naming the measured
benefit and the trigger for removing them again. From code inspection alone it
says "expected to reduce X; verify with Y," never a percentage.

## When to reach for it

Type `/go-turbo`, or the agent reaches for it automatically when a task fits.
It is the only skill here the agent can select on its own; the rest wait for you
to type them.

| Your situation | Where to go |
| --- | --- |
| Writing or refactoring Go where speed or memory is part of the requirement | `go-turbo` |
| Something is already slow and you want to know why | [go-turbo-analyze](go-turbo-analyze.md) |
| You know the fix and want it applied and proven | [go-turbo-improve](go-turbo-improve.md) |
| A diff or a whole repo to check | [go-turbo-review](go-turbo-review.md), [go-turbo-audit](go-turbo-audit.md) |
| Go code with no performance dimension | Nothing here; it will just add ceremony |

It is Go-only by design. The ladder, the escape-analysis material, and the
runtime knobs are all Go-specific, and the description says so to stop it firing
on Rust or Zig.

## The ladder

One idea carries this skill: work the cheapest rung that applies, and stop when
the return stops justifying the complexity.

1. Avoid the work entirely — delete, defer, cache, coalesce, short-circuit.
2. Fix the algorithm and data structure.
3. Reduce hot-path allocation.
4. Remove incidental heap escapes.
5. Amortize boundary crossings — syscalls, queries, RPCs, locks.
6. Bound and remove contention.
7. Only then tune representation and runtime.

The ordering is the whole point. Nothing below rung 2 rescues an avoidable
O(n²), and a clean optimisation in a cold function is still wasted complexity —
so the skill traces the real path before it climbs.

Three intensity levels scope how far it goes: `cruise` for clean idiomatic Go
with safe baseline improvements only, `turbo` (the default) for the full ladder,
`redline` to chase every measured hot-path cost — under the same correctness and
evidence gates, which `redline` does not relax.

## Common questions

**Does loading the skill actually change what the agent produces?**

On the current eval suite, not measurably. Across four tasks and two models the
paired difference between the plain and skill arms sits inside the confidence
interval both times, with the point estimate slightly favouring plain. That is a
null result on an underpowered suite, not a demonstration of equivalence: the
suite cannot resolve effects smaller than about 0.05 for `opus:medium` or 0.21
for `sonnet:high`, one of the four tasks is saturated at the ceiling, and the
honest read is that the effective task count is three. The suite needs harder,
more numerous tasks before it can answer this. Run it yourself with
`./evals/bench.py run` — it is in `evals/`.

**What does it cost?**

Roughly double the tokens per run. In the same sweep the skill arm averaged
376k tokens against 199k for plain on `opus:medium`, and 496k against 277k on
`sonnet:high`. Most of that is reference loading. Reach for `cruise`, or for one
of the focused skills, when the task does not need the whole ladder.

**It refused to add `sync.Pool` and I know the path is hot.**

Then give it the profile. The refusal is the skill working: pooling adds a
lifetime contract that outlives whoever added it, and "the path is hot" from
code reading is a hypothesis. An allocation profile or a benchmark showing the
allocs/op turns it into a change it will make, with a `turbo:` comment recording
why.

## It's working if

- Claims about speed come with a benchstat block or the words "not measured" —
  never a bare percentage.
- It fixes the algorithm before it reaches for a pool.
- Complex optimisations arrive with a comment naming the measured benefit and
  the condition for removing them.
- It says which production, load, or platform gates it did not exercise.
- On a cold path it tells you the optimisation is not worth it, rather than
  performing one.
- It loads two or three references for a task, not the whole knowledge base.

## Where it fits

`go-turbo` is a reach-for-it-anytime standalone, and the core the other seven
are cut from — they are the same judgment scoped to one job, reachable only by
typing them. The usual path through a problem you have not diagnosed yet is
[go-turbo-analyze](go-turbo-analyze.md) then
[go-turbo-improve](go-turbo-improve.md), with
[go-turbo-bench](go-turbo-bench.md) supplying the evidence either step runs on.
[go-turbo-help](go-turbo-help.md) routes you when you are unsure which fits.
