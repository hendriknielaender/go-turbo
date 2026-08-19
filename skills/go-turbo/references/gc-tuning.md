# GOGC and GOMEMLIMIT

The two controls, what each trades, and why the limit has to come from the whole
process budget rather than the heap alone.

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
