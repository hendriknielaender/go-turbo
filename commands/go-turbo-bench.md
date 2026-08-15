---
description: Write, run, and interpret Go benchmarks correctly
argument-hint: "[function or package]"
---

Run the `go-turbo-bench` skill on: $ARGUMENTS

Write benchmarks that resist dead-code elimination (`b.Loop()` or a sink), report allocs, cover the real input size distribution, and use `RunParallel` where contention matters. Run with `-count=10 -benchmem -run=^$` and compare with `benchstat`. Read `p` and `±` before the percentage; never state a speedup without its conditions.
