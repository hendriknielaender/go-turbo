---
name: go-turbo-analyze
description: Diagnose why Go code is slow, ranked and evidence-backed. Changes nothing.
argument-hint: "[path, function, or profile]"
disable-model-invocation: true
---

# go-turbo-analyze

Diagnose, don't fix. The deliverable is a ranked, evidence-backed account of
where the time or memory goes and what each item would cost to address. The user
decides what to act on; `$go-turbo-improve` executes.

The failure mode this exists to prevent is confident guessing — recommending
`sync.Pool` for what turns out to be an O(n²) loop. Rank by evidence strength,
and mark anything unmeasured as unmeasured.

## Procedure

**1. Establish what "slow" means.** Latency, throughput, memory, CPU cost, or
capacity? Which percentile, under what load, on which deployment? Where the user
has not said, infer only what the evidence supports and state the assumption.
One mechanism can move both throughput and tail latency, but the experiment and
the acceptance threshold differ.

**2. Match evidence to the question:**

- production latency, throughput, queue, saturation, and memory metrics;
- CPU, allocation, heap, mutex, or block profiles for their specific costs;
- a short execution trace for scheduler, blocking, and tail-latency behavior;
- representative microbenchmarks for local mechanisms;
- code reading as a hypothesis generator, never as proof of impact.

Where you can run things, run them:

```sh
go test -bench=. -benchmem -run=^$ ./...
go test -run='^$' -bench='BenchmarkTarget$' \
  -cpuprofile=cpu.out -memprofile=mem.out ./pkg
go tool pprof -top -nodecount=25 cpu.out
go build -gcflags='-m=2' ./... 2>&1 | rg 'escapes to heap|moved to heap'
```

For a running service: `/debug/pprof/profile?seconds=30` under load,
`/debug/pprof/heap`, `/debug/pprof/goroutine?debug=1`.

**3. Read the code along the actual hot path.** Trace the real call flow for the
operation in question, not the whole repo, and check each rung of the ladder in
`skills/go-turbo/SKILL.md` in order.

**4. Rank by expected impact.** Biggest win first. Effort and risk are secondary
but stated, because a 30% win behind an unsafe rewrite may lose to a 10% win
that is a one-line change.

## Diagnosis tags

`algo:` wrong complexity class or redundant work — almost always ranks first.
`alloc:` hot-path allocation; name the site and count. `escape:` heap escape
that could stay on the stack. `gc:` cycle rate, live set, or scan cost. `sync:`
contention, unbounded goroutines, channel serialization. `io:` per-item syscall,
round trip, or query. `net:` connection reuse failure, missing timeout,
transport misconfiguration. `leak:` accumulation over time. `layout:` padding,
false sharing, cache behavior.

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

Finding nothing is a real result: `No bottleneck visible at this level. The cost
is elsewhere — instrument <X> and re-run.` Inventing findings to fill a report
wastes the user's afternoon.

## Rules

- **Recommend a paid win only from measurement.** Pooling, `unsafe`, zero-copy
  sharing, sharding, and runtime tuning need evidence. A baseline improvement is
  recommendable once its capacity, lifetime, flush, error, and compatibility
  preconditions are visible in the code.
- **Separate cumulative from flat time.** A function with 90% cumulative and 2%
  flat is a caller, not a bottleneck. Descend before reporting.
- **Match the profile to the question.** `/allocs` shows allocation volume;
  `/heap` is a retained-memory snapshot, so memory growth needs comparable
  snapshots over time. Confusing them sends people the wrong way.
- **Low CPU with bad tail latency points away from local compute.** Inspect
  queues, external waits, scheduler delay, lock/channel blocking, and overload. A
  block profile covers synchronization primitives; an execution trace and request
  telemetry cover the wider path.
- **Attribute retained memory carefully.** `pprof` credits the allocation site,
  so a retained sub-slice appears under whoever allocated the big buffer, not
  whoever holds it.

For profile interpretation read the relevant sections of
[pprof.md](../go-turbo/references/pprof.md); for a diagnosis tag's
domain, use the routing table in `skills/go-turbo/SKILL.md`.

## Boundaries

Reports only, changes nothing — that is what makes it safe to run on unfamiliar
code. Correctness bugs and security issues spotted along the way get one line
and a pointer to a normal review. One-shot, scoped to the current task.
