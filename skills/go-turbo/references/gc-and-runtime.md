# GC and Runtime

Treat the runtime as a measured system. Reduce unnecessary work and live
pointer-rich data before changing collector or scheduler controls. Runtime
knobs trade one resource for another; they do not repair an unbounded live
set, leaked goroutines, missing backpressure, or a poor algorithm.

## Contents

- [Model collector cost](#model-collector-cost)
- [Use GOGC as a memory-for-CPU control](#use-gogc-as-a-memory-for-cpu-control)
- [Set GOMEMLIMIT from the complete process budget](#set-gomemlimit-from-the-complete-process-budget)
- [Diagnose pressure with complementary signals](#diagnose-pressure-with-complementary-signals)
- [Force collection or scavenging only at explicit phase boundaries](#force-collection-or-scavenging-only-at-explicit-phase-boundaries)
- [Use weak pointers for lifetime semantics, not deterministic eviction](#use-weak-pointers-for-lifetime-semantics-not-deterministic-eviction)
- [Keep cleanup nondeterministic and Close explicit](#keep-cleanup-nondeterministic-and-close-explicit)
- [Let GOMAXPROCS follow available CPU by default](#let-gomaxprocs-follow-available-cpu-by-default)
- [Read scheduler pressure as G-M-P state](#read-scheduler-pressure-as-g-m-p-state)
- [Budget goroutines by retained state, not stack folklore](#budget-goroutines-by-retained-state-not-stack-folklore)
- [Use the netpoller instead of rebuilding it](#use-the-netpoller-instead-of-rebuilding-it)
- [Version compatibility](#version-compatibility)

## Model collector cost

Go 1.26 uses a concurrent, tracing, non-generational mark-and-sweep collector.
Short stop-the-world phases establish and finish a cycle; marking runs mostly
with the application, using write barriers and mutator assists to preserve the
object graph while it changes.

The Green Tea marking implementation is enabled by default in Go 1.26. It
batches scan work for better locality, but it does not change the operational
model: roots and reachable pointer-bearing memory must still be scanned, and
allocation still drives new cycles. A build with
`GOEXPERIMENT=nogreenteagc` is useful only as a controlled comparison when a
toolchain upgrade changes a measured workload.

Reason about three quantities:

1. **Allocation rate.** More heap bytes and objects per second consume
   allocator work and reach the next collection sooner.
2. **Live heap and roots.** Reachable heap objects, goroutine stacks, and
   globals determine mark work and the next heap goal.
3. **Scannable bytes.** Pointer-free data is cheaper for the collector to scan
   than a pointer-dense graph, though it still consumes memory, bandwidth, and
   reclamation work.

Do not assume that a short-lived heap object is free because it dies quickly;
the collector remains non-generational. Also do not replace compact values
with pointer graphs merely to reduce copying: that can increase allocations,
retention, cache misses, and scan work simultaneously.

**Optimize the model when:** profiles show allocator or GC CPU, assist time,
or memory pressure. **Backfires when:** code becomes pooled, pointer-free, or
manually packed without a workload-level improvement. Collector internals and
pause distributions change across releases; benchmark the deployed toolchain.

## Use GOGC as a memory-for-CPU control

`GOGC` controls heap growth relative to the live heap and scannable roots left
by the previous cycle. Ignoring pacing adjustments and minimums, the goal is
approximately:

```text
live heap + (live heap + scannable stacks + scannable globals) * GOGC / 100
```

The runtime starts a cycle before that goal so marking can finish near it. A
soft memory limit may lower the goal. The default is `GOGC=100`.

```sh
GOGC=200 ./service
GOGC=50 ./service
GOGC=off ./service
```

- Raise `GOGC` when GC CPU or assists constrain throughput and measured memory
  headroom can absorb a larger heap between cycles.
- Lower `GOGC` when peak managed memory matters more than collector CPU and
  latency remains acceptable under more frequent cycles.
- Use `GOGC=off` only when another explicit policy, normally `GOMEMLIMIT`,
  bounds growth. Forced collections still run, and a memory limit still drives
  GC.

**Backfire cases:** a larger goal amplifies peak memory and may make each cycle
scan a growing live graph; a smaller goal can cause constant collection and
assist work; `off` without a sound limit can reach the process or container
limit before reclamation. Change one variable at a time under representative
allocation rate, live set, and SLO load.

## Set GOMEMLIMIT from the complete process budget

`GOMEMLIMIT` is a soft limit on memory mapped, managed, and not released by the
Go runtime. Its accounting is:

```text
runtime.MemStats.Sys - runtime.MemStats.HeapReleased
```

The equivalent runtime metrics are:

```text
/memory/classes/total:bytes - /memory/classes/heap/released:bytes
```

This includes the Go heap, Go-managed goroutine stacks, and runtime memory such
as allocator and GC metadata. It excludes the mapped executable, memory held
by the kernel, memory managed by non-Go code, and mappings made through
`syscall.Mmap`. C allocations and many C-created thread stacks are therefore
outside the limit.

Derive the value instead of applying a universal percentage:

```text
Go runtime budget = process or cgroup budget
                  - measured peak external memory
                  - measured safety margin
```

Then configure it at startup or at run time:

```sh
GOMEMLIMIT=6GiB ./service
```

```go
previous := debug.SetMemoryLimit(6 << 30)
_ = previous
```

Monitor both the runtime-managed expression and process RSS or cgroup working
set. The limit is not an RSS ceiling or an out-of-memory guard. If the live
managed set itself approaches or exceeds the setting, the runtime can collect
nearly continuously and still remain above it.

Combining `GOGC=off` with a limit can reduce unnecessary cycles for a stable
workload:

```sh
GOGC=off GOMEMLIMIT=6GiB ./service
```

**Use when:** deployment has a real memory budget and external memory has been
measured under peak load. **Backfires when:** cgo, `syscall.Mmap`, executable
mappings, kernel buffers, or workload spikes consume the reserved headroom;
the live set leaves no runway; or several colocated limits are confused. Load
test the failure edge and alert on GC limiter activation, sustained assists,
RSS, and OOM events.

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

## Force collection or scavenging only at explicit phase boundaries

`runtime.GC` forces a complete collection and blocks the caller; it may also
block the whole program. `debug.FreeOSMemory` forces a collection and then asks
the scavenger to return as much memory as possible to the OS. The runtime
already scavenges unused pages in the background.

**Use when:** a test requires a collection boundary, a diagnostic needs a
repeatable heap state, or a measured batch program finishes a known large
phase and can tolerate the latency. **Backfires when:** invoked from request
paths, timers, or memory watchdogs; repeated forcing adds pauses, CPU, and page
faults when memory is needed again. Fix retention and set a budget instead of
turning forced GC into policy.

## Use weak pointers for lifetime semantics, not deterministic eviction

`weak.Pointer[T]` does not keep its target reachable. `Value` may become nil as
soon as the target is unreachable, and collection timing is unspecified:

```go
type Registry struct {
	mu sync.Mutex
	m  map[string]weak.Pointer[Entry]
}

func (r *Registry) Lookup(key string) *Entry {
	r.mu.Lock()
	defer r.mu.Unlock()

	p, ok := r.m[key]
	if !ok {
		return nil
	}
	entry := p.Value()
	if entry == nil {
		delete(r.m, key)
	}
	return entry
}
```

Use weak pointers for canonicalization, identity relationships, or caches that
must not extend an object's lifetime. The returned pointer is a normal strong
reference while reachable.

**Backfire cases:** hit rate follows GC timing, stale map keys remain until
maintenance or lookup, recreating a value can break identity expectations,
and weak references complicate concurrency. Use an explicitly size-bounded
cache for predictable capacity and eviction. Never use weak reachability as a
correctness or resource-release signal.

## Keep cleanup nondeterministic and Close explicit

Release files, sockets, transactions, mappings, and buffers through explicit
`Close`, `Stop`, or `Release` methods. Use `defer` where the lifetime matches a
scope.

`runtime.AddCleanup` can attach a last-resort cleanup to an object. Cleanups:

- may run arbitrarily late or not before process exit;
- run concurrently and without ordering guarantees;
- must not receive an argument or closure that keeps the owner reachable;
- may require `runtime.KeepAlive(owner)` after the last operation that needs
  the owner alive;
- are not guaranteed for some tiny, zero-sized, or linker-allocated objects.

`runtime.SetFinalizer` is harder to reason about: it resurrects the object for
another cycle, finalizers execute sequentially, and cycles or dependencies can
prevent expected execution. Prefer `AddCleanup` for new fallback logic, but
neither API is deterministic resource management.

**Use cleanup when:** wrapping a non-Go resource needs a leak safety net in a
long-running process and explicit close remains the primary path. **Backfires
when:** correctness, flushing, lock release, bounded resource usage, or process
shutdown depends on it; registering cleanup on every tiny object can also add
tracking and scheduling cost.

## Let GOMAXPROCS follow available CPU by default

`GOMAXPROCS` is the number of Ps allowed to execute Go code simultaneously,
not a goroutine or OS-thread limit. In Go 1.26, the default considers logical
CPU count, process affinity, and on Linux the cgroup CPU quota. The runtime can
update the default as those inputs change.

The cgroup input usually represents CPU limit, not Kubernetes CPU request. A
pod with a request but no quota may therefore use the host or affinity CPU
count. A fractional quota is rounded up, so throttling can still occur within
a quota period.

Setting the `GOMAXPROCS` environment variable or calling
`runtime.GOMAXPROCS` disables automatic updates. Call
`runtime.SetDefaultGOMAXPROCS` to restore and immediately recompute the
default. Compatibility controls such as `containermaxprocs` and
`updatemaxprocs` can also disable automatic behavior; check the main module's
Go language version when diagnosing them.

**Override when:** a workload benchmark under its real quota proves that a
fixed lower value improves tail latency, throttling, or co-tenancy, or an
operator intentionally reserves CPUs. **Backfires when:** a fixed value goes
stale after quota or affinity changes, exceeds available CPU and adds
contention, or reduces parallelism needed by application and GC work. Compare
throughput, runnable latency, throttling, GC CPU, and SLO tails together.

## Read scheduler pressure as G-M-P state

The scheduler coordinates:

- **G:** a goroutine and its stack/state;
- **M:** an OS thread;
- **P:** the execution resources required to run Go code.

There are exactly `GOMAXPROCS` Ps. Each P has local runnable work; the runtime
also uses global queues and work stealing. When a goroutine blocks in a system
call, its M can release the P so another M runs Go work. Blocking cgo calls,
system calls, and `runtime.LockOSThread` may still grow the OS-thread count.

Take a bounded scheduler snapshot:

```sh
GODEBUG=schedtrace=1000 ./service
GODEBUG=schedtrace=1000,scheddetail=1 ./service
```

Interpret trends, not one line:

- runnable work with no idle Ps indicates CPU demand or long non-preempted
  work; adding goroutines cannot create CPU capacity;
- rising thread count far above Ps points to blocking calls, cgo, or locked
  threads;
- many waiting goroutines can be healthy I/O concurrency or a leak; classify
  wait reasons in profiles and traces.

`debug.SetMaxThreads` is a crash-before-system-exhaustion safety limit, not a
throughput control. Lowering it without accounting for worst-case syscall,
cgo, and locked-thread demand can crash the process.

**Tune scheduler-facing concurrency when:** traces and load tests show runnable
delay, blocking, or oversubscription. **Backfires when:** worker pools are
sized only from core count despite I/O waits, more goroutines amplify queues
and memory, or scheduler debug output is left enabled without measuring its
diagnostic overhead.

## Budget goroutines by retained state, not stack folklore

At process start on ordinary platforms, new goroutines begin with a 2 KiB Go
stack. Stacks grow by copying and can shrink during GC. Go 1.26 can adapt the
starting size for newly created goroutines after collections based on observed
stack use, so 2 KiB is the initial minimum model, not a permanent per-goroutine
reservation. Platform-specific stack additions may also apply.

Observe the current new-stack size and scan work with:

```text
/gc/stack/starting-size:bytes
/gc/scan/stack:bytes
/sched/goroutines:goroutines
```

At high concurrency, retained request state, timers, channel entries, buffers,
TLS state, and referenced object graphs commonly cost more than the starting
stack. Deep recursion and large local arrays can repeatedly grow and copy
stacks; blocked goroutines retain every reachable frame value.

**Use goroutine-per-operation or connection when:** work blocks naturally,
lifetimes are bounded by cancellation/deadlines, and load tests fit the memory
and scheduler budget. **Backfires when:** admission is unbounded, buffers are
allocated per goroutine, blocked sends have no cancellation, stacks carry
large locals, or goroutine count is used as a substitute for backpressure.

## Use the netpoller instead of rebuilding it

For pollable network descriptors, the runtime integrates platform readiness
mechanisms such as epoll, kqueue, and IOCP. A goroutine waiting for socket
readiness can park without dedicating an OS thread; readiness makes it
runnable again. This makes straightforward blocking-style network code scale
well when deadlines, buffer ownership, and admission are controlled.

Not every operation follows this path. Regular file I/O on common Unix
systems, cgo calls, some name-resolution paths, device I/O, and arbitrary
syscalls may block an OS thread. TLS, compression, parsing, and application
work consume CPU after readiness. Confirm actual blocking and thread behavior
with goroutine profiles and execution traces.

**Keep goroutine-based I/O when:** standard network APIs meet throughput and
tail-latency goals. **Consider a custom event loop only when:** profiles prove
runtime scheduling or per-connection state is the remaining bottleneck and a
benchmark includes cancellation, backpressure, partial I/O, and failures.
Custom loops backfire through portability loss, complex ownership, starvation,
and duplicated runtime behavior. Never remove deadlines or cancellation for
speed.

## Version compatibility

This reference describes Go 1.26 runtime behavior. `GOMEMLIMIT` and
`debug.SetMemoryLimit` require Go 1.19; `runtime.AddCleanup` and `weak.Pointer`
require Go 1.24; container-aware defaults and `SetDefaultGOMAXPROCS` require Go
1.25. Metric names and experiment flags also vary by release. On older
toolchains, keep explicit resource closure, use a deliberately bounded cache
instead of weak reachability, and configure runtime/container limits through
the APIs that release actually supports. Never raise a module's minimum Go
version merely to adopt an optional runtime technique.
