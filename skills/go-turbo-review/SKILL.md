---
name: go-turbo-review
description: >
  Review a Go diff or pull request purely for performance: allocations added
  to hot paths, heap escapes, unbounded goroutines, missing preallocation,
  per-item syscalls or queries, lock contention, missing timeouts, and
  premature optimizations that cost readability for nothing. One line per
  finding with the fix. Use when the user says "review this for performance",
  "perf review", "will this be slow", "review this PR", "any performance
  issues here", "$go-turbo-review", or shares a diff and asks about
  performance impact. Complements correctness review — this one only hunts
  performance.
---

# go-turbo-review

Review the diff for performance. One line per finding: location, what's
wrong, what replaces it. The best outcome is no actionable performance
regression and no speculative complexity.

Two directions matter equally here. Reviewers reliably catch the added
allocation; they reliably miss the `sync.Pool` added to a cold path, which
costs a lifetime bug and buys nothing. Flag both.

## Format

`L<line>: <tag> <what>. <fix>.` — or `<file>:L<line>:` for multi-file diffs.

Tags:

- `alloc:` avoidable allocation on a path that looks hot. Name the fix.
- `escape:` value pushed to the heap by code shape. Name the restructure.
- `algo:` complexity that will not hold at scale — nested scan, repeated
  sort, linear lookup in a loop.
- `sync:` unbounded goroutines, contention, over-wide critical section,
  serialization through a channel.
- `io:` per-item syscall, query, or round trip that should be batched or
  buffered.
- `net:` undrained response body, missing timeout, transport misconfiguration,
  per-request client construction.
- `leak:` goroutine or memory retention — no exit path, unbounded queue,
  retained sub-slice of a large buffer.
- `premature:` optimization with no evidence, costing readability or safety
  for an unmeasured win. Replacement: the simpler code.
- `layout:` struct padding or false sharing worth fixing at this volume.

## Examples

Not this:

> "Have you considered whether this slice could be preallocated? It might
> improve performance under certain conditions."

This:

- `L34: alloc: append into nil slice, len(rows) known. make([]Result, 0, len(rows)).`
- `L12: escape: measured constructor allocation comes from returning *Point; identity and nil are unused. Return Point by value and remeasure.`
- `L88: algo: linear scan of routes inside the request loop, O(n·m). Build the map once at startup.`
- `L51: sync: goroutine per message, unbounded. Use errgroup.SetLimit with a bound derived from the CPU or dependency budget.`
- `L23: io: db.Exec per row inside the loop. Batch with CopyIn or a multi-value insert.`
- `L67: net: this bounded HTTP/1 body is not consumed to EOF before Close, so reuse may be lost. Consume it or deliberately forgo reuse.`
- `L102: leak: queue <- buf[:n] retains the full 32 KB pool buffer per message. Copy first.`
- `L45: premature: sync.Pool for a struct allocated once per request on a config path. Delete it; the lifetime risk buys nothing here.`
- `L9: alloc: string(payload) then back to []byte at L14. Stay in []byte; bytes has the same helpers.`
- `L77: net: a new custom http.Transport is created per request, fragmenting connection pools. Reuse a configured client and transport.`

## Judgment

Diffs get reviewed by people with limited attention, so precision about what
matters is the entire value of this skill.

- **Hot path or not?** An allocation in a startup function or a CLI flag
  parser is not a finding. If you can't tell whether a path is hot, say so:
  `L20: alloc: … — if this is per-request, fix it; if it's startup, ignore.`
- **Baseline or evidence-gated?** Request a simple fix only when its size,
  lifetime, flush, error, and compatibility preconditions are visible. Pooling,
  zero-copy, manual layout, sharding, and `unsafe` require a measurement and
  explicit tradeoff; raise them as experiments, not demands.
- **Don't invent hot paths.** If the diff touches a config loader, review it
  as a config loader.
- **A `turbo:` comment on a deliberate tradeoff is not a finding.** It's the
  author doing the right thing. Read it and check the reasoning holds.
- **Benchmarks and tests are not bloat.** Never flag a benchmark added
  alongside an optimization; that's the standard being met.

## Scoring

End with the estimate that matters:

```
net: -<N> allocs/op on the hot path, -<M> round trips per request.
```

Quantify only what measured evidence can defend. If the diff is clean:
`No actionable performance finding.`

## Boundaries

Performance only. Correctness bugs, security issues, and style go to a normal
review pass — mention them in one line if severe and move on, but don't take
them over. Lists findings, applies nothing. One-shot.

For a whole repository rather than a diff, use `$go-turbo-audit`. To apply
the fixes, `$go-turbo-improve`.
Task-scoped.
