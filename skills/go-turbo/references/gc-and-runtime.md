# GC and Runtime

The garbage collector and the scheduler are the two runtime subsystems that
turn "code that allocates a lot" and "code that blocks a lot" into latency.
Understanding what they actually do is what separates targeted tuning from
cargo-culted environment variables.

## Contents

- [How the collector works](#how-the-collector-works)
- [GOGC](#gogc)
- [GOMEMLIMIT](#gomemlimit)
- [Diagnosing GC pressure](#diagnosing-gc-pressure)
- [Weak pointers](#weak-pointers)
- [Finalizers and cleanups](#finalizers-and-cleanups)
- [GOMAXPROCS](#gomaxprocs)
- [The scheduler](#the-scheduler)
- [The netpoller](#the-netpoller)

## How the collector works

Go's collector is concurrent, non-generational, and tri-color mark-and-sweep.

- **Concurrent** — marking runs alongside your program. Two brief
  stop-the-world pauses bracket the cycle (mark start and mark termination),
  typically well under a millisecond even with large heaps. Write barriers
  keep the mark correct while the program mutates pointers mid-scan.
- **Non-generational** — every object is treated the same. There is no
  cheap "young generation" collection, which is why *rate of allocation*
  matters more in Go than object lifetime does. Short-lived garbage isn't
  cheaper to collect; it's cheaper to never allocate.
- **Tri-color** — objects are white (unreached), grey (reached, not yet
  scanned), or black (reached and scanned). Roots start grey; the collector
  drains the grey set; whatever is still white at the end is unreachable.

The practical consequences:

1. **GC cost scales with the live heap and the pointer density in it**, not
   with garbage. A large heap of pointer-heavy structs is expensive to mark
   every cycle. A large heap of `[]byte` or pointer-free structs is nearly
   free to mark — the collector skips scanning objects with no pointers.
2. **GC frequency scales with allocation rate.** Halving allocations roughly
   halves GC cycles.
3. **The GC steals CPU from your program.** It targets ~25% of `GOMAXPROCS`.
   If GC is eating a quarter of your CPU, that ceiling is the symptom.

Go 1.26 ships the Green Tea collector by default, which improves marking
locality for small objects and reduces GC overhead meaningfully on real
workloads (with extra gains on newer amd64 via vector instructions). It
changes the constants, not the model: allocation rate and live pointer count
are still what you control. `GOEXPERIMENT=nogreenteagc` opts out if you need
to A/B it.

**The lever you actually have is allocation.** Reducing pointer-heavy live
data and cutting allocation rate beats every knob below. Tuning `GOGC`
without first reducing allocation is treating the symptom.

## GOGC

`GOGC` sets the heap growth target: the next collection triggers when the
heap reaches `live × (1 + GOGC/100)`. Default 100 means "collect when the
heap has doubled since the last mark."

```sh
GOGC=100   # default
GOGC=400   # collect 4x less often: more memory, less CPU
GOGC=off   # no pacing-driven GC (pair with GOMEMLIMIT or you will OOM)
```

Raising `GOGC` trades memory for CPU. It helps when:

- the service is CPU-bound with a small live heap and high allocation rate —
  GC is running constantly to reclaim a heap that was never large
- you have headroom in the memory budget and GC shows up as a top CPU
  consumer in profiles

It hurts when the live heap is already large: each cycle then has more to
mark, and you've made the peaks worse without reducing the work.

Documented production cases exist at both extremes — services that cut CPU
substantially by raising `GOGC` with automated memory-pressure feedback, and
low-allocation cryptographic workloads that gained order-of-magnitude
throughput at very high `GOGC` values. Both were driven by profiles, and both
are unusual. Treat a `GOGC` change as an experiment with a control group, not
a config default.

## GOMEMLIMIT

`GOMEMLIMIT` (Go 1.19+) is a soft ceiling on total memory the runtime tries
to stay under. As usage approaches it, the collector runs more aggressively.

```sh
GOMEMLIMIT=6GiB ./service
```

```go
import "runtime/debug"
debug.SetMemoryLimit(6 << 30)
```

This is the single most valuable runtime setting for containerized services,
and its absence is the most common cause of mysterious OOMKills. Without it
the runtime has no idea the cgroup limit exists: it happily grows the heap
past the container's limit and the kernel kills the process.

Set it to roughly 80–90% of the container limit. The gap covers non-heap
memory the limit does not account for — goroutine stacks, OS thread stacks,
mmap'd regions, runtime metadata, and cgo allocations.

The combination worth knowing:

```sh
GOMEMLIMIT=6GiB GOGC=off ./service
```

This lets the heap grow freely and collects only when approaching the
ceiling. It maximizes memory utilization and minimizes GC cycles — excellent
for a service with a known, stable memory budget and predictable live set.
It is dangerous if the live set can spike, because there is no pacing to
catch it early; you go straight from "fine" to "GC thrashing at the limit."
Test it under the real workload before shipping it.

Note also: `GOMAXPROCS` in Go 1.25+ is container-aware and derives a default
from the cgroup CPU limit. Older versions saw the host's core count, which
made services on small CPU shares badly over-parallelized. If you are on an
older runtime, `automaxprocs` or an explicit `GOMAXPROCS` is worth setting.

## Diagnosing GC pressure

Cheapest signal first:

```sh
GODEBUG=gctrace=1 ./service
```

```
gc 42 @18.412s 4%: 0.11+52+0.089 ms clock, 1.7+31/103/0+1.4 ms cpu,
   412->441->198 MB, 424 MB goal, 16 P
```

Read it as: cycle 42, 18.4s in, **4% of total CPU spent on GC since start**,
pause/concurrent/pause in ms, then heap **at start → at mark end → live
after**, and the trigger goal.

- The percentage is the headline. Under ~5% is normal. Above 15–20% means
  allocation rate is your bottleneck.
- Rising live heap across cycles (the third number) means a leak or a growing
  cache, not a GC problem.
- Frequent cycles with a small live heap means high churn — go find the
  allocation.

Then get specifics:

```sh
go tool pprof http://localhost:6060/debug/pprof/allocs   # all allocations
go tool pprof http://localhost:6060/debug/pprof/heap     # live at snapshot
```

`allocs` answers "what is causing GC cycles" (cumulative churn). `heap`
answers "what is holding memory" (live set). They point at different problems
and mixing them up wastes hours. In `pprof`, use `-sample_index=alloc_objects`
to rank by count rather than bytes — many small allocations often cost more
than a few large ones.

For a live view of goroutine growth and heap over time,
`runtime.ReadMemStats` into your metrics pipeline works, but read it
sparingly: it stops the world briefly. `runtime/metrics` is the modern,
cheaper alternative and should be preferred for continuous collection.

## Weak pointers

`weak` (Go 1.24+) provides pointers that do not keep their target alive.

```go
import "weak"

type Cache struct {
    mu sync.Mutex
    m  map[string]weak.Pointer[Entry]
}

func (c *Cache) Get(k string) *Entry {
    c.mu.Lock()
    defer c.mu.Unlock()
    if wp, ok := c.m[k]; ok {
        if e := wp.Value(); e != nil {
            return e
        }
        delete(c.m, k)   // target was collected
    }
    return nil
}
```

The right use is canonicalization maps and caches that must not extend
lifetimes — interning, identity maps, memo tables keyed on objects the
program owns elsewhere. Always nil-check `Value()`; the target can go away
between two lines.

The wrong use is as a general-purpose cache eviction policy. Collection
timing is not under your control, so hit rates are unpredictable. For a cache
you want to *manage*, use an explicit LRU with a size bound.

## Finalizers and cleanups

`runtime.SetFinalizer` is legacy and has sharp edges: it resurrects objects
for an extra cycle, it doesn't run on program exit, and a finalizer on an
object referenced by its own finalizer closure leaks forever.

`runtime.AddCleanup` (Go 1.24+) is the replacement: it doesn't resurrect,
allows multiple cleanups per object, and works with interior pointers. Use it
for releasing non-GC resources (mmap regions, cgo handles) as a backstop.

Neither is a substitute for `Close()` and `defer`. A cleanup that runs "at
some point" is not resource management; it's a safety net for the case where
someone forgot.

## GOMAXPROCS

`GOMAXPROCS` caps how many OS threads execute Go code simultaneously. Each
unit is a P (logical processor) holding a run queue.

Defaults are right in the overwhelming majority of cases. Since Go 1.25 the
default is cgroup-aware on Linux and the runtime re-reads the limit
periodically, so containers get a sane value automatically.

One gotcha worth knowing: it reads the cgroup CPU **limit**, not the request.
A Kubernetes pod with `requests: 2` and no limit still sees every core on the
node, which is the common over-parallelization case. Set a limit, or set
`GOMAXPROCS` explicitly. Setting `GOMAXPROCS` manually (env var or
`runtime.GOMAXPROCS`) disables the automatic behavior, as do the GODEBUG
settings `containermaxprocs=0` and `updatemaxprocs=0`.

Raising it beyond the available cores does not add throughput — it adds
context switches, cache thrashing, and contention on shared runtime
structures including the GC's own work queues. Lowering it below the cores is
occasionally right: it reduces GC worker parallelism and scheduler overhead
for services deliberately capped for co-tenancy.

Change it only with a benchmark on the real workload showing the win.

## The scheduler

Three actors: **G** (goroutine), **M** (OS thread), **P** (logical
processor). A G runs on an M that holds a P. Each P has a local run queue;
there's also a global queue for overflow and for goroutines that arrive
without a P.

Two behaviors worth knowing:

- **Work stealing.** Idle Ps steal from busy peers, which is why goroutine
  imbalance across workers usually self-corrects, and why over-provisioning
  Ps adds balancing overhead for no gain.
- **Syscall handoff.** When a G makes a blocking syscall, its M detaches
  from the P so another M can pick the P up and keep running Go code. This is
  why blocking file I/O doesn't stall the whole program — but it does create
  threads. A service with thousands of concurrent blocking syscalls will
  accumulate OS threads (bounded by 10,000 by default, tunable with
  `debug.SetMaxThreads`), and each thread costs memory.

Inspecting it:

```sh
GODEBUG=schedtrace=1000 ./service               # one line per second
GODEBUG=schedtrace=1000,scheddetail=1 ./service # per-P and per-M detail
```

```
SCHED 3024ms: gomaxprocs=16 idleprocs=2 threads=31 spinningthreads=1
    idlethreads=18 runqueue=4 gcwaiting=false
```

A persistently non-zero `runqueue` with `idleprocs=0` means you are CPU
saturated — more goroutines will not help. `threads` climbing far above
`gomaxprocs` means goroutines are blocking in syscalls or cgo.

For anything more detailed, use the execution tracer rather than reading
schedtrace by eye:

```sh
curl -o trace.out http://localhost:6060/debug/pprof/trace?seconds=5
go tool trace trace.out
```

The tracer shows scheduler latency (time between "runnable" and "running"),
which is the number that actually explains tail latency in a busy service and
which no profile will show you.

## The netpoller

Network I/O does not block threads. When a goroutine reads from a socket
that has no data, the runtime registers the fd with `epoll` (Linux) or
`kqueue` (BSD/macOS) and parks the goroutine; the M is free to run something
else. When the kernel signals readiness, the poller makes the goroutine
runnable again.

This is why goroutine-per-connection scales to tens of thousands of
connections in Go, and why "use an event loop instead" is usually wrong here
— you already have one, underneath. The per-connection cost is the goroutine
stack (starting at 8 KB, growing as needed) plus whatever buffers you keep
alive, so at very high connection counts the memory story is dominated by
your buffer strategy, not by the goroutines.

Files are different: regular file I/O is not pollable on Linux, so it uses
the syscall-handoff path and does consume threads under concurrency.
