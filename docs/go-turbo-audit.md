# go-turbo-audit

## What it does

`go-turbo-audit` is [go-turbo-review](go-turbo-review.md) widened to a whole
repository — the same tags and the same discipline — plus one job the diff
review does not have: assessing whether the repo can tell whether it is fast.

Ranking matters more here than anywhere else. A repo-wide scan surfaces hundreds
of candidates, and a flat list buries the three that matter, so the skill ranks
by expected impact and cuts the tail at roughly twenty findings. A list nobody
finishes is a list nobody starts.

## When to reach for it

Type `/go-turbo-audit` — the agent will not fire it on its own. Pass a path, or
nothing for the whole repo.

Reach for it when you are new to a codebase, preparing a performance push, or
want to know where the measurement gaps are. For a single change, use
[go-turbo-review](go-turbo-review.md).

## Scope first, then measurement coverage

It establishes what the repo *is* before scanning. A CLI tool, a batch job and a
request-serving service have almost disjoint findings, and auditing a CLI for
connection pooling wastes everyone's time. Findings are then weighted by whether
they sit on a real hot path — one in `cmd/migrate` is not equal to one in the
request path.

The second half of the report is the part a diff review has no room for:

- how many benchmarks exist, covering which hot paths, and which have none;
- whether they use `-benchmem` and resist dead-code elimination;
- whether profiles can be captured from the running service at all;
- whether the runtime memory limit reflects the real container budget.

A missing measurement on the top path usually outranks any individual
speculative finding, because it blocks that fix from ever being verified.

It also harvests existing `turbo:` markers as debt. A marker naming a ceiling
but no revisit trigger gets flagged — those are the ones that quietly become
permanent.

## Common questions

**It capped the list at twenty and there is clearly more.**

Deliberate. The cap is what keeps the top three visible, and it tells you it
truncated. Re-run scoped to a subdirectory when you want depth in one area.

**It reported "premature optimisation" findings in code that already works.**

Those are findings by design: `sync.Pool` on a cold path, `unsafe` with no
benchmark, hand-rolled stdlib, GC knobs set in code with no recorded
justification. Each carries risk and buys nothing, and a repo-wide view is the
only place the pattern becomes visible.

## It's working if

- It states what kind of program the repo is before listing anything.
- Findings are ranked and the tail is cut, with the truncation stated.
- The report says how many benchmarks exist and which paths have none.
- It names what it skipped — generated code, vendored dependencies, test helpers.
- Paid wins are raised as questions with a suggested measurement, not demands,
  because repo-wide it has less context than the authors.

## Where it fits

The repository-scoped member of the report-only pair with
[go-turbo-review](go-turbo-review.md). It changes nothing; to act on a finding,
take it to [go-turbo-analyze](go-turbo-analyze.md) for diagnosis and then
[go-turbo-improve](go-turbo-improve.md). [go-turbo-help](go-turbo-help.md)
routes the whole set.
