# go-turbo

`skills/go-turbo/SKILL.md` holds the full workflow, the evidence gate, and the
routes into `skills/go-turbo/references/`. Read it. What follows is the portable
minimum for agents that read only this file.

## Stance

Write clear, idiomatic Go first. Latency, throughput, and memory are
workload-specific measurements, not coding styles. Preserve behavior, errors,
ownership, race freedom, context propagation, cancellation, validation,
deadlines, and resource cleanup.

Work down this ladder and stop when further complexity is not justified:

1. Remove, defer, cache, coalesce, or short-circuit unnecessary work.
2. Choose the right algorithm, data structure, index, and ownership model.
3. Reduce material hot-path allocation and unintended retention.
4. Remove incidental heap escapes confirmed by compiler diagnostics.
5. Amortize syscalls, queries, RPCs, encodes, locks, and handoffs.
6. Bound concurrency and address measured contention or backpressure.
7. Only then tune layout, pooling, the runtime, protocols, or machine details.

## Evidence gate

Anything that adds lifetime rules, aliasing, portability limits, or operational
tuning needs a representative profile, trace, benchmark, or production metric
first — `sync.Pool`, zero-copy sharing, manual padding, sharded or lock-free
synchronization, mmap, raw socket controls, GC knobs, PGO, `unsafe`, assembly,
SIMD. Record the measured benefit, the ownership or portability contract, and the
removal trigger beside the code.

Compare with `-benchmem -count=10` and `benchstat`; report `ns/op`, `B/op`,
`allocs/op`, plus Go version, architecture, and input distribution. Run
`go test -race` for shared-state or concurrency changes. Never claim "faster"
from code inspection — say what remains unmeasured.

## Output

Lead with the code or the verdict. Then the non-obvious tradeoffs, the actual
evidence or `not measured`, the correctness checks, and the next justified rung.
