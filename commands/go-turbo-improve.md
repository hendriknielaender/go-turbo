---
description: Apply a Go performance fix and prove it with benchstat
argument-hint: "[path, function, or finding]"
---

Run the `go-turbo-improve` skill on: $ARGUMENTS

Baseline first (write a benchmark if none exists), fix the highest applicable rung of the ladder, one change per measurement, then verify: `go test ./...`, `go test -race ./...` if concurrency changed, and `benchstat old.txt new.txt`. Behavior must be identical. If benchstat shows no significant change, revert and say so.
