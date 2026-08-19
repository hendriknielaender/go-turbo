---
name: go-turbo-bench
description: Write, run, and read Go benchmarks you can trust.
argument-hint: "[function or package]"
disable-model-invocation: true
---

# go-turbo-bench

Write the benchmark, run it properly, read it honestly.

Most Go benchmarks measure something other than what their author intended, in
four classic ways: the compiler deleted the work, setup got timed, the input was
unrepresentative, or one run was compared against one run and noise was reported
as a win. Guarding against those is most of this job.

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
excludes setup automatically. On older Go, use `b.N` with a package-level sink
and `b.ResetTimer()`:

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

Throughput changes non-linearly with size as you cross cache levels. A single
average hides exactly the transition you care about.

**Benchmark contention separately.** A single-goroutine benchmark of a
mutex-protected structure measures the uncontended fast path — not the case
anyone was worried about:

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

**Per-iteration setup** that resists hoisting:

```go
for b.Loop() {
    b.StopTimer()
    x := freshInput()
    b.StartTimer()
    Process(x)
}
```

Stop/start is expensive; where it dominates, pre-build a slice of inputs and
index by iteration.

## Running

```sh
go test -bench=. -benchmem -run=^$ ./...
go test -bench=BenchmarkParse -benchmem -count=10 -run=^$ ./pkg
go test -bench=. -benchtime=5s ./pkg
```

- `-run=^$` skips tests, keeping their time and side effects out of the run.
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

1. **The distributions and comparison marker.** With benchstat's default test,
   `~` means the collected samples do not distinguish the versions at the
   configured confidence level. Report "no measurable change in this
   experiment," which is a different claim from "identical."
2. **Noise and overlap.** Large run-to-run spread relative to the effect means
   the experiment lacks resolution. Find the noise source or collect a better
   workload before trusting a small delta.
3. **The effect size and metrics.** Interpret `ns/op`, `B/op`, and `allocs/op`
   together; a statistically detectable change can still be operationally
   irrelevant.

Hold the machine, power state, toolchain, flags, inputs, and background load
constant. Interleave or randomize old/new runs where drift or thermal state may
matter. Today's run against last month's on another host measures the
environments as much as the code.

Shared CI runners are often noisy: calibrate a threshold from that runner's
observed variance, or use a dedicated benchmark host for small regressions. CPU
affinity and frequency controls are platform-specific — apply them identically
to both versions, and only when understood.

## Reporting

```
benchstat old.txt new.txt
  <actual output>

reading: <what it means in one sentence>
caveat:  <input distribution, machine, what this does not cover>
```

State a speedup with its conditions: "34% faster on 1 KB inputs, n=10, `p=0.000`,
on this machine" is a claim. "34% faster" is marketing.

## Common traps

- **Sub-nanosecond ns/op** — the compiler deleted the work. Use `b.Loop()` or a
  sink.
- **allocs/op unchanged but ns/op improved a lot** — check the statistics and the
  mechanism. Algorithmic, contention, copying, and instruction-count wins all
  legitimately move time without moving allocations.
- **Benchmark faster, service unchanged** — the function wasn't the bottleneck.
  Go back to profiling.
- **Comparing across Go versions or machines** — that is a different experiment.
  Hold one variable at a time.
- **GC effectively disabled** — a short benchmark may never trigger a collection,
  hiding the GC cost of the allocations it makes. That is precisely why allocs/op
  matters more than ns/op for allocation changes.

## Boundaries

Writes and interprets benchmarks. To find what to benchmark use
`$go-turbo-analyze`; to apply and validate a fix, `$go-turbo-improve`. For
profiling and load-testing workflows read the relevant sections of
[writing-benchmarks.md](../go-turbo/references/writing-benchmarks.md). Scoped to the current
task.
