---
name: go-turbo
description: Write, refactor, review, benchmark, or diagnose Go for performance. Use when latency, throughput, allocation, or memory matters in Go code. Go only.
argument-hint: "[cruise|turbo|redline]"
---

# Go Turbo

Produce the simplest Go implementation that meets the workload. Speed, memory,
throughput, and tail latency are measured properties, not coding styles. Stay
idiomatic until evidence shows a more complex shape earns its maintenance cost.

## Operating contract

1. Preserve behavior, error semantics, cancellation, race freedom, validation,
   deadlines, and resource ownership.
2. Respect the module's minimum Go version. Raising it, or reaching for a newer
   API, needs the task's authorization.
3. Ask only about decisions that change the answer: target SLO, representative
   workload, memory ceiling, compatibility boundary. Otherwise state a safe
   assumption and continue.
4. Make the smallest change that addresses the highest applicable rung. Stop
   when the return stops justifying the complexity.
5. Keep observed evidence and code-reading hypotheses apart. Verify behavior
   first, then measure the question the change was meant to answer.

## Performance ladder

Exhaust each rung before the next.

1. **Avoid work.** Delete, defer, cache, coalesce, short-circuit, or stop after
   cancellation. Compute only what a consumer actually reads.
2. **Choose the algorithm and data structure.** Fix the complexity class,
   repeated scans or sorts, poor indexes, redundant passes. Nothing below
   rescues an avoidable O(n²) path.
3. **Reduce hot-path allocation.** Preallocate realistic known sizes, reuse a
   caller-owned destination, keep one byte/string representation, release
   retained backing arrays.
4. **Remove incidental escapes.** Read compiler diagnostics, then restructure
   only values whose heap lifetime comes from code shape rather than design.
5. **Amortize boundaries.** Batch or buffer syscalls, database operations,
   remote calls, lock acquisitions, channel handoffs.
6. **Bound and remove contention.** Limit concurrency, shorten or shard measured
   critical sections, publish immutable snapshots, enforce backpressure.
7. **Tune representation and runtime.** Layout, false sharing, pools, mmap, PGO,
   GC settings, socket controls, `unsafe`, SIMD, custom protocols — once
   measurement identifies that layer.

Trace the real path before climbing. A clean optimization in a cold function is
still wasted complexity.

## Improvement classes

Ordinary improvements — presizing, `strings.Builder`, buffered I/O, dropping
`string`/`[]byte` round trips, reusing compiled regexps, propagating context —
ship without a profile once their preconditions hold. A short diff is not proof
that a change is free; check the preconditions in `references/workflow.md`.

### Evidence-gated improvements

These add ownership rules, concurrency machinery, portability limits, or
operational tuning, so each needs a representative profile, trace, benchmark, or
production metric first:

- `sync.Pool` and reusable mutable object graphs;
- zero-copy aliasing or caller-visible buffer reuse;
- lock sharding, CAS loops, lock-free structures, cache-line padding;
- structure-of-arrays layouts, manual encoding, custom framing;
- mmap, raw socket options, event loops, thread pinning, CPU affinity;
- `GOGC`, `GOMEMLIMIT`, `GOMAXPROCS`, build experiments, PGO;
- `unsafe`, assembly, experimental SIMD.

Each one ships with a nearby comment naming the measured benefit, the ownership
or portability contract, and the removal trigger — and only ever with the
evidence that comment describes:

```go
// turbo: reuse 32 KiB decode buffers; BenchmarkDecode removed 1 alloc/op.
// Callers must not retain buf after Decode returns. Remove the pool if the
// allocation no longer appears in the production alloc profile.
```

## Verification gate

Run the items whose trigger fires; skip the rest rather than running them for
form.

1. Always: existing and focused behavior tests pass, `go vet` clean.
2. Always: error paths, cancellation, shutdown, and resource cleanup intact.
3. Shared state, goroutines, or channels touched: `go test -race`.
4. Repository ships its own validation: run it.
5. Performance claim made, or evidence-gated change shipped: show before/after
   evidence for it. No claim, no benchmark needed.
6. State the production, load, platform, or hardware gates you left unexercised.

A task with no shared state, no plausibly hot path, and no performance claim is
finished at items 1, 2, and 6.

## Output

Lead with the code or verdict. Then at most one line per non-obvious change, the
actual measurement or `not measured`, the correctness checks, and the next rung
worth investigating. Expand to full detail on request for an audit, report, or
walkthrough.

Report a speedup only from a measurement. From code inspection alone, say
"expected to reduce X; verify with Y." A microbenchmark stays a microbenchmark
claim — end-to-end latency and throughput need end-to-end evidence.

## Reference routing

Paths resolve against this skill's directory, or
`${CLAUDE_PLUGIN_ROOT}/skills/go-turbo/` when that variable is set. Each reference
runs 300–600 lines behind a `## Contents` index: read the section, not the file.

**Measure** — `references/writing-benchmarks.md` writing one you can trust · `references/comparing-benchmarks.md` benchstat, repeats, variance · `references/pprof.md` CPU and memory profiles · `references/block-profiles.md` blocking, mutex, traces · `references/load-testing.md` open-loop, coordinated omission · `references/workflow.md` baseline improvements, intensity levels.

**Allocate** — `references/finding-allocations.md` locating the site · `references/presizing.md` capacity from a bound, and when presizing backfires · `references/interface-boxing.md` conversion vs allocation · `references/pooling.md` sync.Pool · `references/retention.md` sub-slice holding a big array · `references/strings-and-bytes.md` string/[]byte round trips, building · `references/memory-layout.md` padding, false sharing, aliasing.

**Escapes** — `references/escape-analysis.md` reading -gcflags=-m · `references/escape-causes.md` the shapes that escape · `references/necessary-escapes.md` when to leave it · `references/caller-owned-buffers.md` AppendX, reusable storage · `references/value-semantics.md` values, stack scratch · `references/hot-dispatch.md` concrete types, inlining coupling.

**Choose a structure** — `references/choosing-structures.md` from the workload · `references/map-vs-slice.md` the crossover · `references/pointer-density.md` GC cost of layout · `references/sorting.md` sort once, query many · `references/heaps.md` priority queues · `references/monotonic-stacks.md` nested scans in one pass · `references/in-place-transforms.md` filter and compact in place · `references/queues-and-rings.md` bounded queues, rings.

**Run** — `references/gc-cost.md` what the collector spends · `references/gc-tuning.md` GOGC, GOMEMLIMIT · `references/gc-diagnosis.md` gctrace, heap, metrics · `references/object-lifetime.md` weak pointers, cleanups · `references/gomaxprocs.md` CPU quota · `references/scheduler-state.md` G-M-P pressure · `references/goroutine-budgets.md` budget by retained state · `references/netpoll.md` the event loop you already have.

**Compile** — `references/compiler-diagnostics.md` build context, reading decisions · `references/inlining.md` cost model, devirtualization · `references/bounds-check-elimination.md` BCE · `references/pgo.md` profile-guided optimization · `references/build-flags.md` release and target flags · `references/cgo.md` call cost, static linking · `references/build-experiments.md` GOEXPERIMENT, assembly, SIMD.

**Upgrade the toolchain** — `references/upgrade-experiment.md` support status, then the contract · `references/benchmark-inputs.md` deterministic, warm and cold · `references/same-host-comparison.md` one machine, interleaved · `references/sample-variance.md` how many samples · `references/run-metadata.md` what makes it reproducible · `references/interpreting-results.md` canary and rollback.

**Coordinate** — `references/bounding-concurrency.md` fan-out, choosing the bound · `references/backpressure.md` signalling the producer · `references/mutexes-and-atomics.md` cheapest coordination · `references/sharding.md` splitting a contended lock · `references/immutable-snapshots.md` publish, lazy init · `references/channels.md` value ownership · `references/context-cancellation.md` propagating cancellation · `references/graceful-shutdown.md` signals, drain order · `references/goroutine-leaks.md` lifetime and exit paths.

**Cross a boundary** — `references/buffering.md` repeated small I/O · `references/batching.md` grouping without holding locks · `references/stream-copies.md` io.Copy fast paths · `references/framing.md` bounded length prefixes · `references/files-and-mmap.md` file APIs, memory mapping.

**Encode** — `references/json.md` typed and streaming · `references/binary-encoding.md` wire formats, append-oriented · `references/base64.md` exact output sizing · `references/text-processing.md` number formatting, regexps · `references/hashing.md` checksums, streaming hashers · `references/aead-nonces.md` nonce reuse is a security bug · `references/compression.md` codec choice, reuse, bounds.

**Talk to the network** — `references/http-connection-reuse.md` the usual cause · `references/http-client-config.md` transport sharing · `references/httptrace.md` was it reused · `references/request-deadlines.md` timeouts, retry budgets · `references/http-servers.md` server timeouts, release · `references/http2-tuning.md` streams, flow control · `references/tls.md` handshake, resumption · `references/dns.md` resolution, caching · `references/protocol-selection.md` which protocol · `references/http-versions.md` 1.1 vs 2 vs 3 · `references/grpc.md` unary and streaming · `references/tcp-framing.md` raw TCP · `references/udp.md` datagrams · `references/quic.md` streams, migration · `references/socket-options.md` kernel buffers, setsockopt · `references/connection-scale.md` 10k+ connections, accept loops.

**Survive load** — `references/resource-budgets.md` what the process has · `references/admission-control.md` what to accept · `references/rate-limiting.md` limiter algorithms · `references/bounded-queues.md` sizing and full policy · `references/load-shedding.md` shedding, 503s · `references/circuit-breakers.md` stop paying for failure · `references/retries.md` idempotency, budgets, jitter.

Version-specific examples name their minimum version where it matters. On an
older Go release, take the documented fallback and verify it with that exact
toolchain.

Fast is a property you measure, not a style you adopt.
