---
description: Whole-repo Go performance audit — ranked hotlist plus measurement coverage
argument-hint: "[path]"
---

Run the `go-turbo-audit` skill on: $ARGUMENTS (default: the whole repo).

Establish the workload and likely hot paths, then use repository tooling and
code reading to produce a ranked, evidence-labeled hotlist. Assess whether the
important paths have representative benchmarks, profiles, load tests, and
operational limits. Treat PGO and runtime settings as workload-dependent, not
automatic recommendations. Report only; change nothing.
