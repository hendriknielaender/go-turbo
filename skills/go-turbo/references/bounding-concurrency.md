# Bounding Concurrency

Every source of concurrency needs a bound, and the bound belongs at the resource
that saturates — not at the caller that happens to spawn the work.

## Bound every source of concurrency

One goroutine per independent operation is idiomatic when the operation count
is already bounded. It is unsafe when input is unbounded: each goroutine adds
live state, queued work, and pressure on downstream services.

For cancellable work that can fail, a limited `errgroup` is a compact default:

```go
func process(ctx context.Context, items []Item, limit int) error {
	if limit < 1 {
		return fmt.Errorf("worker limit must be positive: %d", limit)
	}

	g, groupCtx := errgroup.WithContext(ctx)
	g.SetLimit(limit)
	for _, item := range items {
		if err := groupCtx.Err(); err != nil {
			break
		}
		g.Go(func() error {
			return handle(groupCtx, item)
		})
	}
	if err := g.Wait(); err != nil {
		return err
	}
	return ctx.Err()
}
```

Every operation called by `handle` must honor `groupCtx`; a concurrency limit
cannot rescue an uninterruptible worker. `SetLimit` must not be changed while
workers are active. Use `TryGo` only when rejection or a fallback path is part
of the contract.

A fixed worker pool is useful for a long-lived stream. Give it one owner that
closes the jobs channel, make result delivery cancellable, and wait for every
worker during shutdown. A semaphore is useful when preserving the existing
call shape matters. Both are capacity bounds, not reasons to keep an
unnecessary pipeline.

Avoid nested independent pools. If an outer request fan-out of 32 invokes an
inner fan-out of 32, the real bound is 1,024. Prefer one shared budget for the
scarce resource.

## Choose the bound from the bottleneck

- CPU work usually starts near `runtime.GOMAXPROCS(0)`. Increase the count only
  when a benchmark shows useful overlap rather than scheduler and cache cost.
- I/O work is bounded by the dependency: connection-pool capacity, rate limit,
  file descriptors, memory per operation, or the peer's tested concurrency.
- Mixed stages deserve separate budgets. A large I/O queue should not multiply
  CPU-heavy parsing behind it.

Sweep the limit under representative load. Watch throughput, tail latency,
queue depth, allocation rate, blocked time, downstream errors, and scheduler
latency. Select the knee of the curve with headroom; the largest number that
survived one test is not a capacity plan.

`GOMAXPROCS` is not a worker-pool size for I/O. Current Go runtimes derive and
periodically update the default from available CPUs, affinity, and supported
container limits. Override it only for an operational reason backed by data.
`runtime.LockOSThread` is for APIs that require thread affinity, not a general
scheduler optimization. OS CPU affinity is likewise deployment policy: it can
reduce migration in a controlled workload or strand the scheduler on the wrong
CPUs, so keep it behind a repeatable system benchmark.
