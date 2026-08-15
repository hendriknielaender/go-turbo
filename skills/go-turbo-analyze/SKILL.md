---
name: go-turbo-analyze
description: >
  Find out why Go code is slow before changing it. Reads the code, profiles
  or benchmarks where possible, and produces a ranked diagnosis: what the
  bottleneck is, what evidence says so, and what the fix would be. Changes
  nothing. Use when the user says "why is this slow", "what's the bottleneck",
  "analyze this Go code", "profile this", "where is the time going", "high
  CPU", "memory keeps growing", "GC is killing us", "$go-turbo-analyze", or
  hands over a pprof profile, benchmark output, or a slow handler and asks
  what's wrong. Use this BEFORE go-turbo-improve — diagnosis first, then fix.
---

# go-turbo-analyze

Diagnose, don't fix. The deliverable is a ranked, evidence-backed account of
where the time or memory goes and what each item would take to address. The
user decides what to act on; `$go-turbo-improve` executes.

The failure mode this skill exists to prevent is confident guessing —
recommending `sync.Pool` for something that turns out to be an O(n²) loop.
Rank by evidence strength, and mark anything unmeasured as unmeasured.

## Procedure

**1. Establish what "slow" means.** Latency, throughput, memory, CPU cost, or
capacity? Which percentile, under what load, on which deployment? If the user
has not said, infer only what the available evidence supports and state the
assumption. The same mechanism can affect throughput and tail latency, but the
experiment and acceptance threshold differ.

**2. Use evidence matched to the question:**

- production latency, throughput, queue, saturation, and memory metrics;
- CPU, allocation, heap, mutex, or block profiles for their specific costs;
- a short execution trace for scheduler, blocking, and tail-latency behavior;
- representative microbenchmarks for local mechanisms;
- code reading as a hypothesis generator, never as proof of impact.

If you can run things, get evidence rather than reading tea leaves:

```sh
go test -bench=. -benchmem -run=^$ ./...
go test -run='^$' -bench='BenchmarkTarget$' \
  -cpuprofile=cpu.out -memprofile=mem.out ./pkg
go tool pprof -top -nodecount=25 cpu.out
go build -gcflags='-m=2' ./... 2>&1 | rg 'escapes to heap|moved to heap'
```

For a running service: `/debug/pprof/profile?seconds=30` under load,
`/debug/pprof/heap`, `/debug/pprof/goroutine?debug=1`.

**3. Read the code along the actual hot path.** Trace the real call flow for
the operation in question — not the whole repo. Check each rung of the
go-turbo ladder in order: redundant work, algorithmic complexity, allocation,
escape, boundary crossings, contention.

**4. Rank by expected impact.** Biggest win first. Effort and risk are
secondary but must be stated, because a 30% win that requires an unsafe
rewrite may lose to a 10% win that's a one-line change.

## Diagnosis tags

- `algo:` wrong complexity class or redundant work. Almost always ranks first.
- `alloc:` allocation on a hot path. Name the site and the count.
- `escape:` heap escape that could stay on the stack.
- `gc:` GC pressure — high cycle rate, large live set, or high scan cost.
- `sync:` lock contention, unbounded goroutines, channel serialization.
- `io:` per-item syscall, round trip, or query that should be batched.
- `net:` connection reuse failure, missing timeout, transport misconfiguration.
- `leak:` goroutine, memory, or connection accumulation over time.
- `layout:` struct padding, false sharing, cache behavior.

## Output

```
<n>. <tag> <file>:<line> — <what is happening>
   evidence: <profile line / benchmark figure / gctrace / "code reading only">
   cost:     <share of the problem, quantified if measured>
   fix:      <the change, one line>
   effort:   <trivial | moderate | invasive>  risk: <low | medium | high>
```

Then:

```
verdict: <the one-sentence answer to "why is it slow">
measured: <yes, via X> | <no — here is what to run to confirm>
```

If nothing meaningful is found, say so: `No bottleneck visible at this
level. The cost is elsewhere — instrument <X> and re-run.` A clean diagnosis
is a real result, and inventing findings to fill a report wastes the user's
afternoon.

## Rules

- **Never recommend a paid win on code reading alone.** Pooling, `unsafe`,
  zero-copy sharing, sharding, and runtime tuning require measurement. A
  baseline improvement can be recommended only when its capacity, lifetime,
  flush, error, and compatibility preconditions are visible in the code.
- **Separate cumulative from flat time.** A function with 90% cumulative and
  2% flat is a caller, not a bottleneck. Descend before reporting.
- **Match the profile to the question.** `/allocs` shows allocation volume;
  `/heap` is a retained-memory snapshot, so memory growth needs comparable
  snapshots over time. Confusing them sends people the wrong way.
- **Low CPU with bad tail latency points away from local compute.** Inspect
  queues, external waits, scheduler delay, lock/channel blocking, and overload.
  A block profile covers synchronization primitives; an execution trace and
  request telemetry cover the wider path.
- **Attribute retained memory carefully.** `pprof` credits the allocation
  site, so a retained sub-slice appears under whoever allocated the big
  buffer, not whoever holds it.

When the core skill is installed alongside this one, load its complete
[measurement reference](../go-turbo/references/measurement.md) for profile
interpretation and use `$go-turbo`'s routing table for the reference matching
the diagnosis tag. This workflow remains usable without those optional
references.

## Boundaries

Reports only, changes nothing — that's what makes it safe to run on
unfamiliar code. Correctness bugs and security issues spotted along the way
get mentioned in one line and routed to a normal review; they are not this
skill's job. One-shot.
Task-scoped.
