# Goroutine Budgets

Budget by retained state, not by stack-size folklore.

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
