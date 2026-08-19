# Blocking and Scheduling

Block and mutex profiles plus the execution trace: what to reach for when CPU is
low and latency is not.

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
