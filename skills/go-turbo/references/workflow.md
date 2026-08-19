# Workflow

How to run a Go performance task once the ladder in `SKILL.md` has told you
which rung you are on: which improvements are safe without a profile, which
tool answers which question, how each request shape changes the job, and what
the intensity levels mean. `comparing-benchmarks.md` owns the before/after procedure
and every rule for reporting a result.

## Baseline improvements that need no profile

Apply these when their preconditions and semantics are clear:

- remove redundant work or select a better complexity class;
- size a slice or map from a known or representative bound;
- use `strings.Builder` or append-style byte APIs for repeated construction;
- buffer repeated small I/O while preserving required flush behavior;
- eliminate needless `string` and `[]byte` round trips;
- reuse immutable compiled regexps, templates, and locations;
- use `sync.OnceValue` or `sync.OnceValues` for ordinary lazy initialization
  when the module supports Go 1.21+, otherwise use `sync.Once`;
- copy a small view before a long-lived consumer would retain a large buffer;
- propagate `context.Context`, close resources, and set network deadlines.

Do not call an improvement free merely because its diff is short. Overlarge
preallocation wastes memory; buffering changes visibility and failure timing;
field order can affect reflection, encoding, cgo, or `unsafe`; a pointer can add
an allocation and GC work. Check the preconditions.

## Matching the tool to the question

- CPU time: CPU profile plus a representative load.
- Allocation churn: allocation profile and `allocs/op`.
- Retained memory: two heap profiles under steady load and a diff.
- Blocking or contention: block/mutex profiles and an execution trace.
- Scheduler or tail latency: a short execution trace under saturation.
- Escape cause: `go build -gcflags='-m -m'`; treat it as diagnosis, not impact.
- Local code change: focused benchmarks on realistic input distributions.
- System change: an open-loop load test with stated concurrency/rate and SLOs.

## Request-specific behavior

- **Write or refactor:** implement idiomatic Go, apply safe baseline
  improvements, and avoid speculative infrastructure. Add a benchmark only
  when performance is a requirement or the chosen design needs evidence.
- **Diagnose:** gather evidence and rank causes; do not modify files unless the
  user also asks for a fix.
- **Optimize:** baseline first, change one coherent mechanism, preserve behavior,
  compare, and revert complexity that does not pay.
- **Review:** report only actionable performance findings on paths plausibly hot;
  flag premature optimization as aggressively as avoidable allocation.
- **Benchmark:** model the real input sizes, warm/cold state, parallelism, and
  outputs; guard against dead-code elimination and setup contamination.
- **Design:** establish workload and SLOs, choose the high-level algorithm and
  ownership model, and leave advanced tuning behind measurable decision gates.

## Intensity levels

Use `turbo` unless the user selects another level. A requested level is scoped
to the current task.

| Level | Behavior |
|---|---|
| `cruise` | Write clean idiomatic Go and apply safe baseline improvements. Do not restructure solely for speed. |
| `turbo` | Enforce the ladder, inspect likely hot paths, and ship evidence-gated changes only when the evidence supports them. |
| `redline` | Investigate every measured hot-path cost and permit low-level techniques, but keep the same correctness and evidence gates. Necessary allocations may remain. |

Invoke explicitly with `$go-turbo`, `$go-turbo cruise`, or `$go-turbo redline`.
