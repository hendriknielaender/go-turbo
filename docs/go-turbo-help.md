# go-turbo-help

## What it does

`go-turbo-help` prints the map: which of the eight skills to reach for, how they
chain, and what the intensity levels mean.

It is a card, not a session. It inspects no code and changes no files, which is
what makes it safe to type when you are not sure what you want yet.

## When to reach for it

Type `/go-turbo-help` — the agent will not fire it on its own, and there is
nothing to pass it.

Reach for it when you know the problem is Go performance but not which skill
fits, or when you want to remember what `redline` does. If you already know the
shape of the task, go straight to the skill.

## The map

| You have | Reach for |
| --- | --- |
| Go to write or refactor, performance in view | [go-turbo](go-turbo.md) |
| Something slow, cause unknown | [go-turbo-analyze](go-turbo-analyze.md) |
| A known fix to apply and prove | [go-turbo-improve](go-turbo-improve.md) |
| A benchmark to write or to distrust | [go-turbo-bench](go-turbo-bench.md) |
| Heap escapes specifically | [go-turbo-escape](go-turbo-escape.md) |
| A diff or PR | [go-turbo-review](go-turbo-review.md) |
| A whole repository | [go-turbo-audit](go-turbo-audit.md) |

[go-turbo](go-turbo.md) is the only one an agent can select for itself. The
other seven wait for you to type them, which is why this card exists at all —
you are the index.

## It's working if

- It prints and stops. No files read, no files changed.
- The path it suggests is one or two skills, not the whole set.

## Where it fits

The router over the set, and the only skill here that does no Go work. It points
at [go-turbo](go-turbo.md)'s `SKILL.md` for the ladder and the evidence gate
rather than summarising them, on the grounds that a summary of the rules is a
second copy that drifts.
