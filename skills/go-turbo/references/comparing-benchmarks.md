# Comparing Benchmarks

One run is a sample of size one. A comparison needs repeats, a held-constant
machine, and a statistical read rather than a percentage.

## Run comparisons

Run behavior tests before timing. Then capture multiple samples from the same
machine and session:

```sh
go test ./...
go test -run='^$' -bench='BenchmarkParse$' -benchmem -count=10 ./pkg > old.txt
# apply one coherent change
go test -run='^$' -bench='BenchmarkParse$' -benchmem -count=10 ./pkg > new.txt
benchstat old.txt new.txt
```

Use an anchored benchmark regexp when the package has unrelated expensive
benchmarks. Increase `-benchtime` when each sample is too short to stabilize:

```sh
go test -run='^$' -bench='BenchmarkParse$' -benchmem -count=10 -benchtime=3s ./pkg
```

Read the distribution and statistical result, not only the percent delta. A
result marked statistically indistinguishable is no measured change. If the
new implementation is more complex, revert it unless another measured metric
justifies the trade.

Do not require allocation movement for a CPU improvement. A better algorithm,
fewer comparisons, vectorized library code, or reduced contention can improve
time while `B/op` and `allocs/op` remain identical.

Profile one representative benchmark run separately from the sample set:

```sh
go test -run='^$' -bench='BenchmarkParse$' -benchtime=10s \
  -cpuprofile=cpu.out -memprofile=mem.out ./pkg
go tool pprof -http=:0 cpu.out
```

## Control and report variance

Use the cheapest effective controls first:

1. Run old and new code on the same host, power mode, Go version, and session.
2. Close noisy applications and allow the machine to reach a stable temperature.
3. Collect enough independent samples and compare them statistically.
4. Warm code/data only when the production question is warm; otherwise preserve
   a cold case and document how it is reset.
5. On dedicated Linux benchmark hosts, pin the governor and CPU set when small
   deltas matter. Record those controls; do not silently apply host-wide tuning.
6. Use dedicated runners for regression thresholds. Shared CI is suitable for
   large regressions unless its variance has been characterized.

Record at least:

```text
commit, dirty state, Go version, GOOS/GOARCH, CPU model, GOMAXPROCS,
benchmark command, input/seed, sample count, benchtime, and relevant env knobs
```

Track per-benchmark coefficient of variation when maintaining a long-lived
suite. Classify noisy tests instead of deleting inconvenient samples. Re-run
only under a documented policy; repeatedly rerunning until a preferred result
appears is selection bias.

For release-to-release comparisons, follow `upgrade-experiment.md` and
`same-host-comparison.md`; run every version on the same hardware and treat the
least stable version as the confidence limit for that benchmark.

## Make defensible claims

A complete claim names:

1. what changed;
2. the metric and direction;
3. the workload/input distribution;
4. baseline and candidate numbers, including allocation metrics;
5. sample count and comparison method;
6. Go version, platform, and relevant configuration;
7. whether the evidence is isolated or end-to-end;
8. correctness and race checks;
9. remaining production or platform gates.

Prefer: “The focused parser benchmark on 64 KiB inputs used 1 fewer alloc/op
and 18% less time across 10 samples on linux/arm64.”

Reject: “The service is 18% faster.”

When measurement is unavailable, state the mechanism as a hypothesis and give
the exact benchmark, profile, or load test needed to decide. That is an honest
result, not an incomplete one.
