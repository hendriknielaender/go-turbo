---
name: go-turbo-bench
description: >
  Write Go benchmarks that measure the right thing, run them correctly, and
  interpret the results with benchstat. Covers b.Loop, sub-benchmarks across
  input sizes, RunParallel for contention, avoiding dead-code elimination,
  and reading statistical significance. Use when the user says "benchmark
  this", "write a benchmark", "is this actually faster", "compare these two
  implementations", "benchstat", "the benchmark says X", "measure this",
  "$go-turbo-bench", or shows benchmark output and asks what it means. Also
  use before claiming any Go optimization worked.
---

# go-turbo-bench

Write the benchmark, run it properly, read it honestly.

Most Go benchmarks measure something other than what their author intended.
The four classic ways: the compiler deleted the work, setup got timed, the
input was unrepresentative, or a single run got compared against a single run
and noise got reported as a win. Guarding against those is most of this job.

## Writing

```go
func BenchmarkParse(b *testing.B) {
    input := loadTestData()      // setup outside the timed region
    b.ReportAllocs()

    for b.Loop() {               // Go 1.24+
        _ = Parse(input)
    }
}
```

`b.Loop()` keeps the loop body's results live (no dead-code elimination) and
excludes setup automatically. On older Go, use `b.N` with a package-level
sink and `b.ResetTimer()`:

```go
var sink Result

func BenchmarkParse(b *testing.B) {
    input := loadTestData()
    b.ReportAllocs()
    b.ResetTimer()

    var r Result
    for i := 0; i < b.N; i++ {
        r = Parse(input)
    }
    sink = r
}
```

**Always `b.ReportAllocs()`.** B/op and allocs/op are near-deterministic and
usually explain the ns/op movement; ns/op alone drifts with machine load.

**Cover the input distribution**, not one convenient case:

```go
func BenchmarkParse(b *testing.B) {
    for _, size := range []int{1 << 10, 64 << 10, 1 << 20} {
        b.Run(fmt.Sprintf("size=%d", size), func(b *testing.B) {
            input := makeInput(size)
            b.ReportAllocs()
            b.SetBytes(int64(size))   // adds MB/s to the output
            for b.Loop() {
                _ = Parse(input)
            }
        })
    }
}
```

Throughput characteristics change non-linearly with size as you cross cache
levels. A single average hides exactly the transition you care about.

**Benchmark contention separately.** A single-goroutine benchmark of a
mutex-protected structure measures the uncontended fast path — which is not
the case anyone was worried about:

```go
func BenchmarkCacheParallel(b *testing.B) {
    c := New()
    b.RunParallel(func(pb *testing.PB) {
        for pb.Next() {
            c.Get("key")
        }
    })
}
```

**Per-iteration setup** that can't be hoisted:

```go
for b.Loop() {
    b.StopTimer()
    x := freshInput()
    b.StartTimer()
    Process(x)
}
```

Stop/start is expensive; if it dominates, pre-build a slice of inputs and
index by iteration instead.

## Running

```sh
go test -bench=. -benchmem -run=^$ ./...
go test -bench=BenchmarkParse -benchmem -count=10 -run=^$ ./pkg
go test -bench=. -benchtime=5s ./pkg
```

- `-run=^$` skips tests, so their time and side effects stay out of the run.
- `-count=10` is required for any comparison. One run is a sample of size one.
- `-benchtime=5s` gives very fast benchmarks enough iterations to stabilize.

## Comparing

```sh
go install golang.org/x/perf/cmd/benchstat@latest

go test -bench=. -benchmem -count=10 -run=^$ ./pkg > old.txt
# change
go test -bench=. -benchmem -count=10 -run=^$ ./pkg > new.txt
benchstat old.txt new.txt
```

Read the result as a set:

1. **The distributions and comparison marker.** With benchstat's default
   test, `~` means the collected samples do not distinguish the versions at
   the configured confidence level. Report "no measurable change in this
   experiment," not "identical."
2. **Noise and overlap.** Large run-to-run spread relative to the effect means
   the experiment lacks resolution. Find the noise source or collect a better
   workload before trusting a small delta.
3. **The effect size and metrics.** Interpret `ns/op`, `B/op`, and `allocs/op`
   together; a statistically detectable change can still be operationally
   irrelevant.

Keep the machine, power state, toolchain, flags, inputs, and background load
constant. Interleave or randomize old/new runs when drift or thermal state may
matter. Comparing today's run against last month's on another host measures
the environments as well as the code.

## Reducing noise

Use a quiet, thermally stable machine; keep power settings fixed; raise
`-count`; and record the environment. CPU affinity or frequency controls are
platform-specific interventions: use them only when understood and apply them
identically to both versions.

Shared CI runners are often noisy. Calibrate a threshold from that runner's
observed variance, or use a dedicated benchmark host for small regressions.

## Reporting

```
benchstat old.txt new.txt
  <actual output>

reading: <what it means in one sentence>
caveat:  <input distribution, machine, what this does not cover>
```

Never state a speedup without its conditions. "34% faster on 1 KB inputs,
n=10, `p=0.000`, on this machine" is a claim. "34% faster" is marketing.

## Common traps

- **Sub-nanosecond ns/op** — the compiler deleted the work. Use `b.Loop()`
  or a sink.
- **allocs/op unchanged but ns/op improved a lot** — check the statistics and
  mechanism. Algorithmic, contention, copying, and instruction-count wins can
  legitimately change time without changing allocations.
- **Benchmark faster, service unchanged** — the function wasn't the
  bottleneck. Go back to profiling.
- **Comparing across Go versions or machines** — that's a different
  experiment. Hold one variable at a time.
- **Benchmarking with GC effectively disabled** — a short benchmark may never
  trigger a collection, hiding the GC cost of the allocations it makes. That
  is precisely why allocs/op matters more than ns/op for allocation changes.

## Boundaries

Writes and interprets benchmarks. For finding what to benchmark, use
`$go-turbo-analyze`; for applying and validating a fix, `$go-turbo-improve`.
When the core skill is installed alongside this one, load its complete
[measurement reference](../go-turbo/references/measurement.md) for profiling
and load-testing workflows. This workflow remains usable without that optional
reference. Task-scoped.
