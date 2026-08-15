---
description: Apply a Go performance fix and prove it with benchstat
argument-hint: "[path, function, or finding]"
---

Run the `go-turbo-improve` skill on: $ARGUMENTS

Baseline behavior and the stated performance question first. Fix the highest
applicable rung with one coherent mechanism, then run focused tests,
`go test -race` for concurrency changes, and an appropriate before/after
comparison. Revert added complexity that has no measurable benefit; retain a
simple correctness or algorithmic improvement without inventing a speedup.
