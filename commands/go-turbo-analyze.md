---
description: Diagnose why Go code is slow — ranked, evidence-backed, changes nothing
argument-hint: "[path, function, or profile]"
---

Run the `go-turbo-analyze` skill on: $ARGUMENTS

Diagnose only — do not modify code. Gather evidence first (profiles, benchmarks, `-gcflags=-m`, `gctrace`), then walk the go-turbo ladder along the actual hot path. Produce a ranked list with a tag, the evidence behind each finding, the fix, and effort/risk. Mark anything based on code reading alone as unmeasured.
