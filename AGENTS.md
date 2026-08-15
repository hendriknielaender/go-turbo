# go-turbo

Use `skills/go-turbo/SKILL.md` for Go implementation and performance work.
It contains the full workflow and routes to focused references. These rules
are the portable minimum for agents that read only `AGENTS.md`.

## Engineering stance

Write clear, idiomatic Go first. Treat latency, throughput, and memory as
workload-specific measurements. Preserve behavior, error handling, ownership,
race freedom, context propagation, cancellation, validation, deadlines, and
resource cleanup.

Work down this ladder and stop when further complexity is not justified:

1. Remove, defer, cache, coalesce, or short-circuit unnecessary work.
2. Choose the right algorithm, data structure, index, and ownership model.
3. Reduce material hot-path allocation and unintended retention.
4. Remove incidental heap escapes confirmed by compiler diagnostics.
5. Amortize syscalls, queries, RPCs, encodes, locks, and handoffs.
6. Bound concurrency and address measured contention or backpressure.
7. Only then tune layout, pooling, the runtime, protocols, or machine details.

## Safe baseline

Apply ordinary, semantics-preserving improvements when their preconditions are
known:

- preallocate from an exact or defensible bound, not an untrusted maximum;
- use append-style byte APIs or `strings.Builder` for repeated construction;
- buffer repeated small I/O only with an explicit flush and error contract;
- avoid needless `string` and `[]byte` round trips;
- reuse immutable compiled regexps, templates, locations, clients, and
  transports where their APIs support concurrent reuse;
- copy a small view when a longer-lived owner would retain a large buffer;
- bound fan-out and queues, propagate cancellation, and set network deadlines.

Do not assume pointers are cheaper than values. Do not reorder exported or
wire-visible structs casually. Do not preallocate from attacker-controlled
sizes. Do not add concurrency merely to make code look parallel.

## Evidence gate

Require a representative profile, trace, benchmark, or production metric
before adding lifetime rules, aliasing, portability limits, or operational
tuning. This includes `sync.Pool`, zero-copy sharing, manual padding,
sharded/lock-free synchronization, mmap, raw socket controls, GC knobs, PGO,
`unsafe`, assembly, and SIMD.

For a justified complex optimization, record the measured benefit, workload,
ownership or portability contract, and removal trigger next to the code. Never
claim “faster” from code inspection alone.

For local comparisons, run focused benchmarks with `-benchmem -count=10` and
compare with `benchstat`. Report `ns/op`, `B/op`, and `allocs/op`, plus Go
version, architecture, and input distribution. Run `go test -race` for shared
state or concurrency changes. State any production or load gate not exercised.

## Output

Lead with code or the verdict. Then state non-obvious tradeoffs, actual evidence
or `not measured`, correctness checks, and the next justified rung.
