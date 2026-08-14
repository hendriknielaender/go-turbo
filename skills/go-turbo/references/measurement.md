# Measurement

An optimization without a measurement is a guess with extra steps. This file
is the part of the skill that keeps the rest honest.

## Contents

- [Writing a benchmark that measures the right thing](#writing-a-benchmark-that-measures-the-right-thing)
- [Running benchmarks](#running-benchmarks)
- [benchstat](#benchstat)
- [Controlling variance](#controlling-variance)
- [pprof](#pprof)
- [Reading a CPU profile](#reading-a-cpu-profile)
- [Memory profiles](#memory-profiles)
- [Block and mutex profiles](#block-and-mutex-profiles)
- [Execution traces](#execution-traces)
- [Load testing](#load-testing)
- [What benchmarks don't tell you](#what-benchmarks-dont-tell-you)

## Writing a benchmark that measures the right thing

```go
func BenchmarkParse(b *testing.B) {
    input := loadTestData()   // setup outside the timed region
    b.ReportAllocs()
    b.ResetTimer()

    for b.Loop() {            // Go 1.24+
        _ = Parse(input)
    }
}
```

`b.Loop()` (Go 1.24+) is the current idiom and fixes two long-standing traps
at once: the loop body's results are kept alive so the compiler can't
eliminate them, and setup before the loop isn't timed. On older versions,
`for i := 0; i < b.N; i++` plus a package-level sink:

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
    sink = r    // keeps the work observable
}
```

**The four ways benchmarks lie:**

1. **Dead code elimination.** An unused result can be deleted entirely,
   giving you a benchmark of an empty loop. Symptom: sub-nanosecond `ns/op`.
2. **Setup inside the timed region.** Allocating test data per iteration
   measures your allocator, not your function. Use `b.ResetTimer()`, or
   `b.StopTimer()`/`b.StartTimer()` around per-iteration setup (which is
   slow — prefer restructuring).
3. **Unrepresentative input.** A parser benchmarked on a 40-byte document
   tells you about function call overhead. Benchmark the size distribution
   you actually see, as sub-benchmarks:

```go
for _, size := range []int{1 << 10, 64 << 10, 1 << 20} {
    b.Run(fmt.Sprintf("size=%d", size), func(b *testing.B) { ... })
}
```

4. **Warm caches and zero contention.** A single-goroutine benchmark of a
   mutex-protected structure shows the uncontended fast path, which is not
   the case you were worried about. Use `b.RunParallel` for concurrent
   behavior:

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

Always `b.ReportAllocs()`. B/op and allocs/op are far more stable than ns/op
and usually explain it.

## Running benchmarks

```sh
go test -bench=. -benchmem -run=^$ ./...
go test -bench=BenchmarkParse -benchmem -count=10 -run=^$ ./pkg
go test -bench=. -benchtime=5s ./pkg          # longer per-benchmark run
go test -bench=. -benchtime=1000x ./pkg       # fixed iteration count
```

- `-run=^$` skips tests so their time and side effects don't pollute the run.
- `-count=10` is not optional if you intend to compare. One run is a sample
  of size one.
- `-benchtime=5s` helps very fast benchmarks accumulate enough iterations to
  stabilize.

Capture profiles from the same run:

```sh
go test -bench=BenchmarkParse -cpuprofile=cpu.out -memprofile=mem.out ./pkg
go tool pprof -http=:8080 cpu.out
```

## benchstat

Never compare two raw benchmark outputs by eye. `benchstat` does the
statistics.

```sh
go install golang.org/x/perf/cmd/benchstat@latest

go test -bench=. -benchmem -count=10 -run=^$ ./pkg > old.txt
# ... make the change ...
go test -bench=. -benchmem -count=10 -run=^$ ./pkg > new.txt

benchstat old.txt new.txt
```

```
                │   old.txt   │              new.txt               │
                │   sec/op    │   sec/op     vs base               │
Parse/size=1024   1.842µ ± 2%   1.203µ ± 1%  -34.69% (p=0.000 n=10)

                │   old.txt    │              new.txt               │
                │     B/op     │     B/op      vs base              │
Parse/size=1024   4.125Ki ± 0%   0.000Ki ± 0%  -100.00% (p=0.000 n=10)
```

Read `p` and `±`, not just the percentage. `p ≥ 0.05` or `~` in the delta
column means the difference is not statistically distinguishable from noise —
report that as "no measurable change," not as a win. A `±` above about 5%
means the benchmark is too noisy to trust small deltas; fix the noise before
believing the number.

## Controlling variance

Modern hardware is actively hostile to benchmarking. Clock frequency scales
with load and temperature, the OS migrates threads between cores, and other
processes compete for cache. Two identical runs can differ by 5–30% with no
controls.

In rough order of value:

1. **Close everything else.** Browsers and IDEs are the biggest source of
   noise on a dev machine.
2. **Increase `-count` and let `benchstat` handle it.** More samples beats
   most environmental fixes and costs nothing but time.
3. **Pin CPU frequency** (Linux): set the governor to `performance`, and
   disable turbo boost — turbo gives brief unsustainable spikes, so a
   benchmark that catches a turbo window looks faster than one that runs
   after thermal throttling.
4. **Pin to cores.** `taskset -c 2,3` avoids core 0 (which handles
   interrupts) and prevents mid-run migration.
5. **Run on a quiet, dedicated machine.** Shared CI runners are the worst
   case: noisy neighbors, unknown CPU models, aggressive throttling. CI
   benchmark numbers are useful for catching order-of-magnitude regressions
   and nothing finer.

A useful discipline for tracked benchmarks: compute the coefficient of
variation (stddev/mean) per benchmark and label anything above ~15% as
unstable rather than deleting it. Knowing a benchmark is inherently noisy is
information; silently comparing against it is a mistake.

Run both the old and new versions in the same session on the same machine.
Comparing today's numbers against last month's on a different host measures
the hosts.

## pprof

For a service, expose the endpoints:

```go
import _ "net/http/pprof"

go func() {
    log.Println(http.ListenAndServe("localhost:6060", nil))
}()
```

Bind to localhost or put it behind auth — these endpoints expose memory
contents and can be used to stall a process.

```sh
go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30   # CPU
go tool pprof http://localhost:6060/debug/pprof/heap                 # live heap
go tool pprof http://localhost:6060/debug/pprof/allocs               # all allocs
go tool pprof http://localhost:6060/debug/pprof/goroutine            # stacks
go tool pprof http://localhost:6060/debug/pprof/block                # blocking
go tool pprof http://localhost:6060/debug/pprof/mutex                # contention
```

**Profile under load.** A profile of an idle service shows you the idle
loop. Generate representative traffic, then capture.

The web UI is where the useful views are:

```sh
go tool pprof -http=:8080 cpu.out
```

Top / Graph / **Flame Graph** / Peek / Source. Flame graph first: width is
time, and the widest plateau is where your time is.

Comparing profiles is underused and excellent:

```sh
go tool pprof -http=:8080 -base=before.out after.out
```

## Reading a CPU profile

Distinguish **flat** (time in this function's own instructions) from
**cumulative** (including everything it calls). A high-cumulative,
low-flat function is a router, not a bottleneck — descend into it.

What the common patterns mean in a Go service:

- **`runtime.mallocgc` high** — allocation-bound. Go to
  `references/allocation.md`; the callers list tells you where.
- **`runtime.gcBgMarkWorker`, `gcDrain`, `scanobject` high** — GC-bound,
  which is the same problem one step later. Fix allocation, not `GOGC`.
- **`runtime.mapaccess`/`mapassign` high** — hashing dominates. Consider a
  slice with linear scan for small n, a better key type (string hashing is
  not free), or fewer lookups.
- **`syscall.Syscall` / `runtime.read` high** — I/O-bound. Buffer or batch;
  see `references/io-and-syscalls.md`.
- **`runtime.futex`, `lock2`, `semacquire` high** — lock contention. Go to
  the mutex profile; see `references/concurrency.md`.
- **`runtime.growslice` high** — missing preallocation.
- **`runtime.convT*`** — interface boxing.
- **`runtime.memmove` high** — copying. Look for unnecessary
  `[]byte`↔`string` conversions or slice copies.
- **`runtime.morestack` high** — deep call chains repeatedly growing
  goroutine stacks. Usually recursion or a very large stack frame in a hot
  goroutine.
- **`gcWriteBarrier` visible** — many pointer writes; sometimes fixable by
  storing indices instead of pointers in a hot structure.

## Memory profiles

Two different questions, two different endpoints:

- **`/debug/pprof/allocs`** — cumulative allocation since start. Answers
  "what is driving GC?" Use `-sample_index=alloc_objects` to rank by count
  rather than bytes; many small allocations often cost more than a few big
  ones.
- **`/debug/pprof/heap`** — live objects at the moment of sampling. Answers
  "what is holding memory?" This is the leak-hunting profile.

For leaks, take two heap profiles minutes apart under steady load and diff:

```sh
go tool pprof -http=:8080 -base=heap1.out heap2.out
```

Anything growing is your suspect. Remember that `pprof` attributes memory to
the *allocation site*, so a retained sub-slice shows up under whoever
allocated the big buffer, not under whoever is holding it — see the
retained-backing-array trap in `references/allocation.md`.

Heap profiling samples (roughly one per 512 KB by default;
`runtime.MemProfileRate` adjusts it). Small, frequent allocations may be
under-represented in a short window.

## Block and mutex profiles

Off by default because they cost something. Enable with sampling:

```go
runtime.SetBlockProfileRate(10_000)   // ~1 sample per 10µs blocked
runtime.SetMutexProfileFraction(100)  // ~1 in 100 contention events
```

- **Block profile** — where goroutines wait: channel operations, mutex
  acquisition, network I/O, `WaitGroup.Wait`. This is where latency hides
  that a CPU profile cannot show, because a blocked goroutine uses no CPU.
- **Mutex profile** — specifically lock contention, attributed to the
  *holder* of the lock. That's the function to shorten or shard.

A service with low CPU utilization and bad p99 latency is a block-profile
problem, not a CPU-profile problem.

## Execution traces

```sh
curl -o trace.out 'http://localhost:6060/debug/pprof/trace?seconds=5'
go tool trace trace.out
```

The trace shows what no profile can: scheduler latency (time between a
goroutine becoming runnable and actually running), GC phases against the
timeline, per-goroutine blocking, and syscall duration.

Use it when the question is "why is p99 bad when the CPU is idle" or "what is
happening during these latency spikes." Keep the window short — traces are
large and analysis gets unwieldy past a few seconds.

The "Goroutine analysis" and "Synchronization blocking profile" views are the
fastest paths to an answer for most services.

## Load testing

Benchmarks measure functions; load tests measure systems. Both are necessary
and neither substitutes for the other.

- **`wrk`** — maximum throughput from a fixed connection count. Best for
  "how fast can this get."
- **`vegeta`** — a *fixed request rate*, which is what you want for latency
  measurement. Open-loop generation avoids coordinated omission, where a
  closed-loop client stops sending during a stall and never records how bad
  it was.
- **`k6`** — scripted, multi-step user flows with ramping stages. Best for
  realistic behavior and CI thresholds.

```sh
echo "GET http://localhost:8080/api/items" > targets.txt
vegeta attack -rate=500 -duration=60s -targets=targets.txt \
  | tee results.bin | vegeta report
vegeta report -type='hist[0,10ms,50ms,100ms,500ms,1s]' < results.bin
```

Report percentiles, not averages. The mean latency of a service with a 5%
tail at 2 seconds looks fine and is not. p50, p95, p99, and max, at a stated
request rate.

Capture a CPU profile *while the load test runs* — that's the profile that
reflects reality.

## What benchmarks don't tell you

Worth stating plainly, because it's the difference between using numbers well
and being misled by them.

A microbenchmark runs one function in a tight loop with warm caches, no
competing goroutines, no GC pressure from adjacent subsystems, no network
jitter, and a fixed input. Your production service runs hundreds of
goroutines, GCs mid-request, and sees inputs varying by orders of magnitude.

The benchmark tells you how that function behaves in isolation. That is
genuinely useful — it's how you know a change helped rather than hurt — and
it is not the same as knowing your service got faster.

Specific gaps to keep in mind:

- **CPU model matters.** Crypto, SIMD-eligible loops, and cache-sensitive
  code behave differently across Intel, AMD, and ARM. A result from one
  microarchitecture doesn't transfer.
- **Core count matters.** GC pause distribution and scheduler contention at
  4 cores say little about 64.
- **Loopback isn't a network.** Networking benchmarks over localhost measure
  Go's stack, not end-to-end behavior.
- **A 3% benchmark delta is usually noise.** A 15% delta with a low `p` and
  tight `±` is a signal. Know which one you have before shipping a claim.

The honest form of a performance claim names its conditions: "30% fewer
allocations per request on this benchmark with this input distribution,
measured with `benchstat` over 10 runs" — not "30% faster."
