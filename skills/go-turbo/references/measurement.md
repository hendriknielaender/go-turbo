# Measurement

Measure the decision the code change is meant to support. A benchmark answers
how one isolated operation behaves under stated conditions; a profile explains
where a running program spends a sampled resource; a load test shows how a
system behaves as demand changes. Do not substitute one for another.

## Contents

- [Define the question](#define-the-question)
- [Build trustworthy benchmarks](#build-trustworthy-benchmarks)
- [Model inputs and state](#model-inputs-and-state)
- [Run comparisons](#run-comparisons)
- [Control and report variance](#control-and-report-variance)
- [Use pprof](#use-pprof)
- [Read CPU and memory profiles](#read-cpu-and-memory-profiles)
- [Measure blocking and scheduling](#measure-blocking-and-scheduling)
- [Load-test systems](#load-test-systems)
- [Make defensible claims](#make-defensible-claims)

## Define the question

Write down the target before selecting a tool:

- latency: p50, p95, p99, or maximum at a stated offered load;
- throughput: operations or bytes per second within a latency/error budget;
- CPU: cores or CPU-seconds per unit of useful work;
- allocation: bytes and objects per operation, plus allocation rate;
- memory: steady live set, peak resident set, or retained objects;
- concurrency: queue delay, blocked time, lock wait, scheduler delay, or leaks;
- startup and binary size: cold process measurements, not a warmed benchmark.

Also name the production dimensions that can change the result: Go version,
GOOS/GOARCH, CPU, core quota, input sizes, hit ratio, concurrency, transport,
TLS state, cache state, and downstream latency. If those are unknown, label the
result exploratory.

## Build trustworthy benchmarks

Use `b.Loop` on Go 1.24 and later. Setup before its first call and cleanup after
it returns are excluded automatically, and the compiler keeps work inside the
loop observable.

```go
func BenchmarkParse(b *testing.B) {
	input := makeInput(64 << 10)
	b.ReportAllocs()
	b.SetBytes(int64(len(input)))

	for b.Loop() {
		result, err := Parse(input)
		if err != nil {
			b.Fatal(err)
		}
		_ = result
	}
}
```

For older toolchains, use `b.N` and publish the final result to a package-level
sink. Do not mix `b.Loop` and `b.N` in one benchmark.

```go
var parseSink Result

func BenchmarkParseLegacy(b *testing.B) {
	input := makeInput(64 << 10)
	b.ReportAllocs()
	b.ResetTimer()

	var result Result
	for i := 0; i < b.N; i++ {
		result, _ = Parse(input)
	}
	parseSink = result
}
```

Check these failure modes:

- **Eliminated work:** implausibly tiny timings often mean the result was not
  observable. Keep outputs and externally visible mutations alive.
- **Timed setup:** building fixtures, opening connections, or generating random
  data inside the loop measures setup. Move it out unless setup is the target.
- **Accumulating state:** appending forever, filling a map, or advancing a reader
  makes every iteration different. Reset state deliberately.
- **Hidden setup cost:** pooling or reusing an object outside the loop measures a
  warm path. Include a separate cold benchmark if initialization matters.
- **Error-path drift:** ignoring errors can turn later iterations into a cheap
  failure path. Check errors inside the loop when they are possible.
- **Global contention:** benchmarks running in parallel may share package state.
  Make that intentional or isolate it.

Report allocation in every performance benchmark. For a focused allocation
contract, `testing.AllocsPerRun` can assert a stable ceiling, but avoid brittle
exact counts around compiler-dependent code unless that count is the API's goal.

Use `b.SetBytes` for byte-oriented work so output includes throughput. Use
`b.ReportMetric` for domain units that make the result interpretable:

```go
func BenchmarkBatch(b *testing.B) {
	const records = 500
	b.ReportAllocs()
	for b.Loop() {
		consume(records)
	}
	b.ReportMetric(records, "records/op")
}
```

## Model inputs and state

Benchmark the distribution, not a convenient specimen. Use sub-benchmarks for
sizes and shapes that cross meaningful boundaries:

```go
func BenchmarkLookup(b *testing.B) {
	for _, size := range []int{8, 128, 4096} {
		b.Run(fmt.Sprintf("n=%d", size), func(b *testing.B) {
			index, keys := buildIndex(size)
			b.ReportAllocs()
			for b.Loop() {
				_, _ = index[keys[size/2]]
			}
		})
	}
}
```

Cover, when relevant:

- success, miss, malformed, and worst-valid inputs;
- small, median, high-percentile, and maximum accepted sizes;
- empty, sparse, dense, sorted, and adversarial distributions;
- warm and cold caches, pools, connections, TLS sessions, and DNS state;
- uncontended and representative contended access;
- single-operation latency and sustained batches;
- the actual protocol negotiated, not merely the requested protocol.

Use deterministic fixtures. Seed a private pseudo-random generator with a fixed
value and record it; do not use global nondeterminism or map iteration order as
input generation. Keep a separate fuzz/property test for correctness diversity.

For synchronization code, use `RunParallel` and vary parallelism. An
uncontended mutex benchmark cannot answer a contention question.

```go
func BenchmarkCacheParallel(b *testing.B) {
	cache := newCache()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			_, _ = cache.Get("hot-key")
		}
	})
}
```

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

For release-to-release comparisons, follow
`toolchain-upgrades.md`; run every version on the same hardware and treat the
least stable version as the confidence limit for that benchmark.

## Use pprof

For a service, expose profiles on a separately protected listener. Never expose
them directly to untrusted networks; profiles and handlers can reveal sensitive
data and consume substantial resources.

```go
import (
	"log"
	"net/http"
	_ "net/http/pprof"
)

func serveProfiles() {
	server := &http.Server{
		Addr:              "127.0.0.1:6060",
		ReadHeaderTimeout: 2 * time.Second,
	}
	log.Print(server.ListenAndServe())
}
```

Capture under the workload that exhibits the problem:

```sh
curl -o cpu.out 'http://127.0.0.1:6060/debug/pprof/profile?seconds=30'
curl -o heap.out 'http://127.0.0.1:6060/debug/pprof/heap'
curl -o allocs.out 'http://127.0.0.1:6060/debug/pprof/allocs'
go tool pprof -http=:0 cpu.out
```

Use profile differences when the baseline is meaningful:

```sh
go tool pprof -base=before.out after.out
```

Sampling changes what can be seen. Short profiles miss rare work; heap sampling
can underrepresent small allocations. Increase duration or sampling only with a
clear need and account for overhead.

## Read CPU and memory profiles

In CPU profiles, **flat** time is time attributed to a function itself;
**cumulative** time includes callees. Descend from high-cumulative/low-flat
callers before naming the bottleneck.

Common clues are starting points, not conclusions:

- allocator and GC frames: inspect their callers and an allocation profile;
- `runtime.growslice`: check capacity knowledge and append volume;
- map hashing/access: reduce lookups or reconsider the key/index;
- copying/memory movement: inspect conversions, growth, and ownership transfers;
- syscall frames: measure operation size and boundary frequency;
- semaphore/lock frames: use mutex and block profiles;
- stack growth: inspect recursion, large frames, and goroutine lifetime.

Use allocation and heap profiles for different questions:

- `allocs`: cumulative churn; identify what drives allocation rate and GC work;
- `heap`: live objects at capture; identify retention and live-set growth.

For a leak, capture two heap profiles after comparable warmup and offered load,
then diff them. Profiles attribute bytes to allocation sites, not to the code
that later retained the object; follow ownership from the allocation.

## Measure blocking and scheduling

Enable synchronization profiles deliberately because they add overhead:

```go
runtime.SetBlockProfileRate(10_000)
runtime.SetMutexProfileFraction(100)
```

- The block profile samples time waiting on synchronization primitives such as
  channels, mutexes, and `select`. Do not treat it as a complete network-I/O
  latency profile.
- The mutex profile attributes contention to lock holders; shorten, move, or
  shard the measured critical section rather than optimizing a waiter.
- The goroutine profile shows current stacks and is useful for growth/leak
  comparisons.

Use an execution trace for scheduler delay, network blocking, syscalls, GC
phases, and cross-goroutine causality:

```sh
curl -o trace.out 'http://127.0.0.1:6060/debug/pprof/trace?seconds=5'
go tool trace trace.out
```

Keep traces short. Use them when low CPU coexists with bad tail latency, when
goroutines remain runnable but unscheduled, or when a profile cannot explain a
timeline spike.

## Load-test systems

Choose the generator by the question:

- use an open-loop fixed-rate generator for latency at a known offered load;
- use a closed-loop/high-throughput generator to find a saturation ceiling;
- use scripted scenarios for realistic multi-step behavior;
- use protocol-specific tools for raw TCP, HTTP/2, gRPC, or QUIC and assert the
  protocol actually negotiated.

Closed-loop clients pause submissions while the service is slow and can hide
the requests that would have arrived during the stall. Call out coordinated
omission whenever reporting latency from such a test.

Test a rate curve rather than one point: below expected load, at target, near
saturation, and beyond saturation. Report offered rate, achieved throughput,
errors/rejections, p50/p95/p99/max latency, CPU, memory, GC, queue depth, open
connections, and downstream saturation.

Separate warm and cold connection-pool/TLS-session tests. For high connection
churn, watch the load generator's file descriptors, CPU, ephemeral ports, and
`TIME_WAIT`; a saturated generator can make a healthy server appear slow.

Capture profiles during the steady portion of the load test, not during idle
startup or uncontrolled ramp-up.

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
