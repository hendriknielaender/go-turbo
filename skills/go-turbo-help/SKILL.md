---
name: go-turbo-help
description: >
  Show the go-turbo skill family, its performance ladder, evidence rules,
  and common Go measurement commands. Use when the user invokes
  $go-turbo-help or asks how to use the go-turbo Go performance skills.
---

# Go Turbo Help

Display this card. Do not inspect code, change files, or claim that a mode
persists beyond the current task.

## Skills

| Skill | Use it for |
| --- | --- |
| `$go-turbo` | Implement, refactor, debug, or review Go with performance-aware idioms. |
| `$go-turbo-analyze` | Diagnose a latency, throughput, CPU, memory, or scaling problem without changing code. |
| `$go-turbo-improve` | Apply a measured performance fix while preserving behavior. |
| `$go-turbo-escape` | Explain and reduce relevant heap escapes. |
| `$go-turbo-bench` | Design, run, and interpret trustworthy Go benchmarks. |
| `$go-turbo-review` | Review a diff for performance risks and unjustified complexity. |
| `$go-turbo-audit` | Produce a ranked, whole-repository performance assessment. |
| `$go-turbo-help` | Show this card. |

Each invocation is task-scoped. The primary `$go-turbo` skill can also be
selected automatically for Go implementation and performance work when the
host supports implicit skill selection.

## Decision ladder

Work from the highest-leverage question downward and stop when further
complexity is not justified:

1. Can the work be removed, cached, deferred, or coalesced?
2. Is the algorithm and data structure appropriate for real input sizes?
3. Are allocations, conversions, or retained objects material?
4. Are values escaping or keeping larger objects live unnecessarily?
5. Are syscalls, RPCs, queries, encodes, or locks paid per item?
6. Is concurrency bounded, cancellable, and free of measured contention?
7. Only then consider layout, pooling, runtime tuning, `unsafe`, or
   architecture-specific techniques.

## Evidence rule

Apply simple, semantics-preserving choices when their preconditions are
known: exact or bounded capacity, amortized builders for repeated assembly,
reused clients and transports, bounded concurrency, deadlines, and retained
slice copies when ownership crosses a lifetime boundary.

Require a representative benchmark or profile before adding lifetime,
aliasing, portability, or maintenance risk. This includes `sync.Pool`,
zero-copy sharing, manual padding, lock-free code, GC tuning, `unsafe`, SIMD,
and protocol or kernel tuning. Record the workload, result, tradeoff, and
revisit trigger next to a deliberate paid optimization.

Never trade race freedom, error handling, cancellation, input validation,
or network deadlines for speed.

## Measurement commands

```sh
go test -bench='BenchmarkTarget$' -benchmem -count=10 -run='^$' ./pkg > old.txt
# make one change
go test -bench='BenchmarkTarget$' -benchmem -count=10 -run='^$' ./pkg > new.txt
benchstat old.txt new.txt

go test -race ./...
go build -gcflags='-m=2' ./... 2>&1 | rg 'escapes to heap|moved to heap'
go tool pprof -top cpu.out
go tool pprof -top allocs.out
go tool trace trace.out
```

Report the Go version, target, machine, workload, statistical comparison,
`ns/op`, `B/op`, and `allocs/op`. A benchmark is not a production latency or
capacity claim unless it models that system boundary.

## Knowledge map

The primary skill routes to focused references under
`skills/go-turbo/references/` for data structures, allocation, escape
analysis, GC/runtime behavior, concurrency, I/O, encoding, networking,
protocols, resilience, measurement, compiler behavior, and toolchain
upgrades.

## Output contract

For normal tasks: code or findings first, then the evidence, tradeoffs, and
next justified rung. Say `not measured` when no valid measurement exists.
