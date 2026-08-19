# Writing Benchmarks

Most Go benchmarks measure something other than what their author intended.
Guarding against that — dead-code elimination, timed setup, unrepresentative
input — is most of the work.

## Contents

- [Define the question](#define-the-question)
- [Build trustworthy benchmarks](#build-trustworthy-benchmarks)
- [Model inputs and state](#model-inputs-and-state)

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
