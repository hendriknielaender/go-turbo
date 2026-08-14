---
name: go-turbo-bench
description: >
  Write Go benchmarks that measure the right thing, run them correctly, and
  interpret the results with benchstat. Covers b.Loop, sub-benchmarks across
  input sizes, RunParallel for contention, avoiding dead-code elimination,
  and reading statistical significance. Use when the user says "benchmark
  this", "write a benchmark", "is this actually faster", "compare these two
  implementations", "benchstat", "the benchmark says X", "measure this",
  "/go-turbo-bench", or shows benchmark output and asks what it means. Also
  use before claiming any Go optimization worked.
license: MIT
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

Read three things, in this order:

1. **`p`** — `p ≥ 0.05` or `~` in the delta column means no statistically
   distinguishable difference. Report that as "no measurable change." It is a
   result, not a failure.
2. **`±`** — variance. Above ~5% means the benchmark is too noisy for small
   deltas; fix the noise before trusting the number.
3. **The percentage** — only once the first two check out.

Both versions must run in the same session on the same machine. Comparing
today's run against last month's on another host measures the hosts.

## Reducing noise

In descending order of value: close other applications; raise `-count`; pin
CPU frequency (governor to `performance`, turbo off — a turbo window makes a
run look fast that a thermally-throttled one doesn't get); pin cores with
`taskset -c 2,3`, avoiding core 0; use a quiet dedicated machine.

Shared CI runners are the worst case. CI benchmark numbers catch
order-of-magnitude regressions and nothing finer — set thresholds
accordingly rather than pretending they're precise.

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
- **allocs/op unchanged but ns/op improved a lot** — suspect measurement
  error before celebrating.
- **Benchmark faster, service unchanged** — the function wasn't the
  bottleneck. Go back to profiling.
- **Comparing across Go versions or machines** — that's a different
  experiment. Hold one variable at a time.
- **Benchmarking with GC effectively disabled** — a short benchmark may never
  trigger a collection, hiding the GC cost of the allocations it makes. That
  is precisely why allocs/op matters more than ns/op for allocation changes.

## Boundaries

Writes and interprets benchmarks. For finding what to benchmark, use
`/go-turbo-analyze`; for applying and validating a fix, `/go-turbo-improve`.
Load `references/measurement.md` from the `go-turbo` skill for profiling and
load-testing workflows.

"stop go-turbo-bench" or "normal mode" to revert.
