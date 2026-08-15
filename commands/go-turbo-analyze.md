---
description: Diagnose why Go code is slow — ranked, evidence-backed, changes nothing
argument-hint: "[path, function, or profile]"
---

Run the `go-turbo-analyze` skill on: $ARGUMENTS

Diagnose only — do not modify code. Gather the evidence appropriate to the
question (profiles, traces, benchmarks, production metrics, or
`-gcflags='-m=2'`), then walk the go-turbo ladder along the actual path.
Produce a ranked list with the evidence, expected mechanism, fix, and
effort/risk. Mark code-reading hypotheses as unmeasured.
