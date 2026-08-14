---
description: Whole-repo Go performance audit — ranked hotlist plus measurement coverage
argument-hint: "[path]"
---

Run the `go-turbo-audit` skill on: $ARGUMENTS (default: the whole repo).

Establish what the repo is and where its hot paths are, then scan with the compiler and linters before reading code. Produce a ranked hotlist (cap ~20), report measurement coverage (benchmarks, pprof, PGO, GOMEMLIMIT), harvest `turbo:` markers, and end with the top three things to do first. Report only — change nothing.
