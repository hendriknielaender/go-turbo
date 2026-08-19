# GOMAXPROCS

Let it follow available CPU by default; a container quota is the case where the
default has historically been wrong.

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

## Version compatibility

This reference describes Go 1.26 runtime behavior. `GOMEMLIMIT` and
`debug.SetMemoryLimit` require Go 1.19; `runtime.AddCleanup` and `weak.Pointer`
require Go 1.24; container-aware defaults and `SetDefaultGOMAXPROCS` require Go
1.25. Metric names and experiment flags also vary by release. On older
toolchains, keep explicit resource closure, use a deliberately bounded cache
instead of weak reachability, and configure runtime/container limits through
the APIs that release actually supports. Never raise a module's minimum Go
version merely to adopt an optional runtime technique.
