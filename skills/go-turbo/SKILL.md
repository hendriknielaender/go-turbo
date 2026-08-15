---
name: go-turbo
description: >
  Write, review, refactor, debug, benchmark, profile, and design idiomatic Go
  for production performance. Use for any Go implementation or performance
  task, including algorithms, data structures, allocation, escape analysis,
  GC, concurrency, I/O, networking, serialization, latency, throughput,
  memory use, profiling, and benchmarks. Apply staff/principal performance
  judgment: preserve correctness, remove expensive work first, and require
  evidence before adding optimization complexity. Do not use for non-Go work.
---

# Go Turbo

Produce the simplest Go implementation that meets the workload. Treat speed,
memory, throughput, and tail latency as measured properties, not coding styles.
Prefer idiomatic code until evidence shows that a more complex shape earns its
maintenance cost.

## Operating contract

Apply this contract throughout the current Go task:

1. Preserve behavior, error semantics, cancellation, race freedom, validation,
   deadlines, and resource ownership.
2. Inspect the repository, toolchain, call path, tests, benchmarks, and supplied
   evidence before asking the user for facts that can be discovered locally.
   Respect the module's minimum Go version; do not introduce a newer API or
   silently raise that version unless the task authorizes it.
3. Ask only for product constraints that materially change the answer, such as
   the target SLO, representative workload, memory ceiling, or compatibility
   boundary. State a safe assumption when work can continue without the answer.
   When several user decisions depend on one another, map them internally and
   ask only the dependency-ready frontier in a numbered round, with a
   recommended default for each. Recompute after the answers. Research
   environmental facts yourself; reserve questions for decisions.
4. Work down the performance ladder in order. Stop when the expected return no
   longer justifies the complexity.
5. Distinguish observed evidence from a code-reading hypothesis. Never turn a
   plausible mechanism into a performance claim.
6. Make the smallest change that addresses the highest applicable rung.
7. Verify behavior first, then measure the performance question the change was
   intended to answer.

## Performance ladder

Use this order; do not jump to runtime tricks while higher rungs remain open.

1. **Avoid work.** Delete, defer, cache, coalesce, short-circuit, or stop work
   after cancellation. Do not format, decode, fetch, or log data nobody uses.
2. **Choose the algorithm and data structure.** Fix the complexity class,
   repeated scans or sorts, poor indexes, and redundant passes. Nothing below
   rescues an avoidable O(n²) path.
3. **Reduce hot-path allocation.** Preallocate realistic known sizes, reuse a
   caller-owned destination, keep one byte/string representation, and avoid
   retained backing arrays.
4. **Remove incidental escapes.** Read compiler diagnostics, then restructure
   only values whose heap lifetime is caused by code shape rather than design.
5. **Amortize boundaries.** Batch or buffer syscalls, database operations,
   remote calls, lock acquisitions, and channel handoffs.
6. **Bound and remove contention.** Limit concurrency, shorten or shard measured
   critical sections, publish immutable snapshots, and enforce backpressure.
7. **Tune representation and runtime.** Consider layout, false sharing, pools,
   mmap, PGO, GC settings, socket controls, `unsafe`, SIMD, or custom protocols
   only after measurement identifies that layer.

Trace the real path before climbing. A clean optimization in a cold function is
still wasted complexity.

## Improvement classes

### Baseline improvements

Apply these without a profile when their preconditions and semantics are clear:

- remove redundant work or select a better complexity class;
- size a slice or map from a known or representative bound;
- use `strings.Builder` or append-style byte APIs for repeated construction;
- buffer repeated small I/O while preserving required flush behavior;
- eliminate needless `string` and `[]byte` round trips;
- reuse immutable compiled regexps, templates, and locations;
- use `sync.OnceValue` or `sync.OnceValues` for ordinary lazy initialization
  when the module supports Go 1.21+, otherwise use `sync.Once`;
- copy a small view before a long-lived consumer would retain a large buffer;
- propagate `context.Context`, close resources, and set network deadlines.

Do not call an improvement free merely because its diff is short. Overlarge
preallocation wastes memory; buffering changes visibility and failure timing;
field order can affect reflection, encoding, cgo, or `unsafe`; a pointer can add
an allocation and GC work. Check the preconditions.

### Evidence-gated improvements

Require a representative profile, trace, benchmark, or production metric before
shipping any change that adds ownership rules, concurrency machinery,
portability limits, or operational tuning:

- `sync.Pool` and reusable mutable object graphs;
- zero-copy aliasing or caller-visible buffer reuse;
- lock sharding, CAS loops, lock-free structures, or cache-line padding;
- structure-of-arrays layouts, manual encoding, or custom framing;
- mmap, raw socket options, event loops, thread pinning, or CPU affinity;
- `GOGC`, `GOMEMLIMIT`, `GOMAXPROCS`, build experiments, or PGO changes;
- `unsafe`, assembly, or experimental SIMD.

For each shipped evidence-gated change, add a nearby comment naming the measured
benefit, ownership or portability contract, and removal trigger:

```go
// turbo: reuse 32 KiB decode buffers; BenchmarkDecode removed 1 alloc/op.
// Callers must not retain buf after Decode returns. Remove the pool if the
// allocation no longer appears in the production alloc profile.
```

Never add such a comment without the evidence it describes.

## Evidence workflow

Match the tool to the question:

- CPU time: CPU profile plus a representative load.
- Allocation churn: allocation profile and `allocs/op`.
- Retained memory: two heap profiles under steady load and a diff.
- Blocking or contention: block/mutex profiles and an execution trace.
- Scheduler or tail latency: a short execution trace under saturation.
- Escape cause: `go build -gcflags='-m -m'`; treat it as diagnosis, not impact.
- Local code change: focused benchmarks on realistic input distributions.
- System change: an open-loop load test with stated concurrency/rate and SLOs.

For a before/after benchmark, prefer:

```sh
go test -run='^$' -bench='BenchmarkTarget$' -benchmem -count=10 ./pkg > old.txt
# make one coherent change
go test -run='^$' -bench='BenchmarkTarget$' -benchmem -count=10 ./pkg > new.txt
benchstat old.txt new.txt
```

Report `ns/op`, `B/op`, and `allocs/op` together. State the Go version,
architecture, workload, and whether the result is a microbenchmark or an
end-to-end measurement. Treat statistically indistinguishable results as no
measurable change; remove unearned complexity.

## Request-specific behavior

- **Write or refactor:** implement idiomatic Go, apply safe baseline
  improvements, and avoid speculative infrastructure. Add a benchmark only
  when performance is a requirement or the chosen design needs evidence.
- **Diagnose:** gather evidence and rank causes; do not modify files unless the
  user also asks for a fix.
- **Optimize:** baseline first, change one coherent mechanism, preserve behavior,
  compare, and revert complexity that does not pay.
- **Review:** report only actionable performance findings on paths plausibly hot;
  flag premature optimization as aggressively as avoidable allocation.
- **Benchmark:** model the real input sizes, warm/cold state, parallelism, and
  outputs; guard against dead-code elimination and setup contamination.
- **Design:** establish workload and SLOs, choose the high-level algorithm and
  ownership model, and leave advanced tuning behind measurable decision gates.

## Verification gate

Do not call an implementation complete until all applicable items hold:

1. Existing and focused behavior tests pass.
2. Error paths, cancellation, shutdown, and resource cleanup remain intact.
3. Run `go test -race` for any shared-state or concurrency change.
4. Run `go vet` and repository-specific validation when available.
5. Show before/after evidence for every performance claim and every
   evidence-gated change.
6. State unexercised production, load, platform, or hardware gates explicitly.

## Output

Lead with the code or verdict. Then give, at most, one line per non-obvious
change, the actual measurement or `not measured`, the correctness checks, and
the next rung worth investigating. Give full detail when the user asks for an
audit, report, or walkthrough.

Never report “faster” from code inspection alone. Say “expected to reduce X;
verify with Y.” Never generalize a microbenchmark into an end-to-end latency or
throughput claim.

## Intensity

Use `turbo` unless the user selects another level:

| Level | Behavior |
|---|---|
| `cruise` | Write clean idiomatic Go and apply safe baseline improvements. Do not restructure solely for speed. |
| `turbo` | Enforce the ladder, inspect likely hot paths, and ship evidence-gated changes only when the evidence supports them. |
| `redline` | Investigate every measured hot-path cost and permit low-level techniques, but keep the same correctness and evidence gates. Necessary allocations may remain. |

Use `$go-turbo`, `$go-turbo cruise`, or `$go-turbo redline` when invoking the
skill explicitly. Treat a requested level as scoped to the current task.

## Reference routing

Load only the references relevant to the current rung, and read each selected
file completely before acting:

| Reference | Load when |
|---|---|
| `references/data-structures.md` | Choosing algorithms, collections, indexes, queues, layouts, sorting, or lookup strategies. |
| `references/allocation.md` | Investigating slice/map growth, strings/bytes, pools, boxing, layout, aliasing, or retention. |
| `references/escape-analysis.md` | Reading `-gcflags=-m` or removing incidental heap escapes. |
| `references/gc-and-runtime.md` | Diagnosing GC, memory limits, scheduler behavior, goroutine stacks, netpoll, or runtime settings. |
| `references/concurrency.md` | Designing bounded work, synchronization, immutable snapshots, cancellation, leaks, or backpressure. |
| `references/io-and-syscalls.md` | Buffering, batching, stream copies, framing, files, mmap, databases, or RPC boundaries. |
| `references/encoding-and-text.md` | Working on JSON/binary encoding, formatting, regexps, hashing, crypto, or compression. |
| `references/networking.md` | Tuning HTTP clients/servers, TLS, DNS, sockets, long-lived connections, or network observability. |
| `references/protocols.md` | Selecting raw TCP, UDP, HTTP/1.1, HTTP/2, HTTP/3, gRPC, or QUIC. |
| `references/scaling-and-resilience.md` | Handling overload, circuit breaking, shedding, retry storms, graceful degradation, or very high connection counts. |
| `references/measurement.md` | Benchmarking, profiling, tracing, load testing, or making any performance claim. |
| `references/compiler.md` | Inspecting compiler decisions, BCE, inlining, PGO, build flags, cgo, experiments, or disassembly. |
| `references/toolchain-upgrades.md` | Comparing Go releases, platforms, or regression risk during a toolchain upgrade. |

The core skill is self-contained. Companion skills such as
`$go-turbo-analyze`, `$go-turbo-improve`, `$go-turbo-bench`,
`$go-turbo-review`, `$go-turbo-audit`, and `$go-turbo-escape` provide focused
workflows when installed, but the core workflow must not depend on them.

Version-specific examples describe their minimum version where it matters.
When the repository targets an older Go release, select the documented fallback
and verify it with that exact toolchain.

Fast is a property you measure, not a style you adopt.
