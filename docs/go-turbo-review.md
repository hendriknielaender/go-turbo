# go-turbo-review

## What it does

`go-turbo-review` reviews a diff for performance and nothing else, one line per
finding: where it is, what is wrong, what replaces it.

It flags optimisation as readily as it flags cost. Reviewers reliably catch the
added allocation and reliably miss the `sync.Pool` added to a cold path, which
buys nothing and costs a lifetime bug — so `premature:` is a tag alongside
`alloc:` and `algo:`, and the suggested replacement is the simpler code. The
best outcome it can report is no actionable regression and no speculative
complexity.

## When to reach for it

Type `/go-turbo-review` — the agent will not fire it on its own. Pass a diff, a
PR, or a set of files.

| Your situation | Where to go |
| --- | --- |
| A diff or PR to check for performance | `go-turbo-review` |
| A whole repository | [go-turbo-audit](go-turbo-audit.md) |
| You want the findings applied, not listed | [go-turbo-improve](go-turbo-improve.md) |
| Correctness, security, or style | A normal review pass — this one gives them a line and moves on |

## Precision is the product

Diffs get reviewed by people with limited attention, so the value is in what it
declines to say. An allocation in a startup function or a flag parser is not a
finding. Where it cannot tell whether a path is hot, it says so in the finding
itself rather than guessing in either direction.

Findings read as replacements, not questions:

> `L88: algo: linear scan of routes inside the request loop, O(n·m). Build the map once at startup.`

rather than "have you considered whether this could be preallocated?" It closes
with a net estimate — allocations or round trips per request — quantified only
where measured evidence can defend it.

A `turbo:` comment in the diff is treated as the author having done the right
thing: it reads the reasoning and checks it holds, rather than flagging the
tradeoff as a finding.

## Common questions

**It said "if this is per-request, fix it; if it's startup, ignore."**

That is the honest answer when the diff does not show the call site, and it is
preferred to a confident guess in either direction. Give it the surrounding
files and the hedge resolves.

**Why does it flag optimisations at all? Someone did the work.**

Because unjustified optimisation carries risk and buys nothing, which makes it a
regression in everything except speed. Pooling, zero-copy, manual layout,
sharding and `unsafe` get raised as experiments needing a measurement — not as
demands — but they do get raised.

## It's working if

- Every finding fits one line and names its replacement.
- Cold-path findings are absent, or explicitly marked as uncertain.
- At least as much attention goes to complexity added as to cost added.
- Benchmarks and tests in the diff are treated as the standard being met, never
  as bloat.
- A clean diff gets `No actionable performance finding.` rather than filler.

## Where it fits

The diff-scoped member of the report-only pair with
[go-turbo-audit](go-turbo-audit.md), which is this skill widened to a repository
and given one extra job. It lists findings and applies nothing; hand them to
[go-turbo-improve](go-turbo-improve.md) to act on one, or
[go-turbo-analyze](go-turbo-analyze.md) if a finding needs diagnosis first.
[go-turbo-help](go-turbo-help.md) routes the whole set.
