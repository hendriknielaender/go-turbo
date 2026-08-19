# Diagnosing GC Pressure

No single signal tells the story. Read gctrace, heap profiles, and runtime
metrics together.

## Diagnose pressure with complementary signals

### Export runtime metrics

Prefer `runtime/metrics` for continuous telemetry. Sample a supported set in
one call and track rates or distributions where appropriate:

```text
/gc/heap/allocs:bytes
/gc/heap/allocs:objects
/gc/heap/live:bytes
/gc/heap/goal:bytes
/gc/scan/heap:bytes
/gc/scan/stack:bytes
/cpu/classes/gc/total:cpu-seconds
/cpu/classes/gc/mark/assist:cpu-seconds
/gc/limiter/last-enabled:gc-cycle
/sched/goroutines:goroutines
/sched/goroutines/runnable:goroutines
/sched/latencies:seconds
```

Discover metric availability with `runtime/metrics.All`; the set can evolve.
Use `runtime.ReadMemStats` for a synchronous point-in-time allocator snapshot,
not as a high-frequency metrics loop.

### Read one collection at a time

Use a short diagnostic run with:

```sh
GODEBUG=gctrace=1 ./service
```

A Go 1.26 line includes cycle number, time since start, cumulative GC CPU
percentage, phase wall/CPU times, heap at start/end/live, heap goal, scannable
stacks and globals, and the P count. The text format is explicitly subject to
change. Compare cycle frequency, live heap, goal, assist CPU, and pauses before
and during the incident; avoid universal percentage thresholds detached from
the service's CPU and latency budget.

### Separate churn from retention

```sh
go tool pprof -sample_index=alloc_objects http://localhost:6060/debug/pprof/allocs
go tool pprof -sample_index=alloc_space http://localhost:6060/debug/pprof/allocs
go tool pprof -sample_index=inuse_space http://localhost:6060/debug/pprof/heap
```

- Allocation object count locates high-frequency churn.
- Allocation space locates cumulative byte volume.
- In-use heap locates what remains reachable at the profile snapshot.

Memory profiles are sampled and a heap profile reflects a recent completed GC
state. Confirm a fix with `-benchmem` and production metrics. Keep profiling
endpoints on an authenticated administrative interface; profiles expose
process details and add overhead.

### Use a trace for latency coupling

Capture a bounded execution trace when runnable delay, blocking, assists, or
stop-the-world pauses need correlation:

```sh
curl -o trace.out 'http://localhost:6060/debug/pprof/trace?seconds=5'
go tool trace trace.out
```

**Use each signal when:** it answers its specific question. **Backfires when:**
a long trace perturbs a busy process, cumulative allocations are mistaken for
live memory, RSS is compared directly with heap live, or one snapshot is
treated as a trend.
