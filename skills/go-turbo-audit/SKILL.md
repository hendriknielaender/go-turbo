---
name: go-turbo-audit
description: Audit a whole Go repo for performance: ranked hotlist plus measurement coverage.
argument-hint: "[path]"
disable-model-invocation: true
---

# go-turbo-audit

`$go-turbo-review`, repo-wide. Same tags, same discipline, wider scope, and one
extra job: assess whether the repo can even tell whether it's fast.

Ranking matters more here than in a diff review. A repo-wide scan surfaces
hundreds of candidates, and a flat list of them buries the three that matter.
Rank by expected impact and cut the tail.

## Scope first

Ask, or infer and state, what the repo *is*. A CLI tool, a batch job, and a
request-serving service have different hot paths and almost disjoint findings;
auditing a CLI for connection pooling wastes everyone's time.

Then find the actual hot paths — HTTP/gRPC handlers, message consumers, the main
processing loop — and weight findings by whether they sit on one. A finding in
`cmd/migrate` is not equal to a finding in the request path.

## Scan

Use compiler and repository tooling early. Compiler diagnostics explain code
shape; runtime impact needs a measurement:

```sh
go vet ./...
go build -gcflags='-m=2' ./... 2>&1 | rg 'escapes to heap|moved to heap'
go test -bench=. -benchmem -run='^$' ./... 2>&1  # only when the suite is bounded and safe
```

Where project linters exist, use their configured checks as candidates and
confirm each on a relevant path. Enabling a new linter to manufacture findings
inverts the job.

Then read for the patterns static analysis misses:

**Allocation** — `append` into a nil slice where the length is known; `make`
without capacity; `+=` string building in loops; `[]byte`↔`string` round trips;
`fmt.Sprintf` on hot paths; per-iteration allocation that could be hoisted;
regexps or templates compiled per call.

**Concurrency** — `go` statements over unbounded input; goroutines with no exit
path; channels used as hot-path queues; a single mutex over a structure touched
by everything; `sync.Map` used as a general-purpose map; `sync.RWMutex` guarding
very short critical sections.

**I/O** — queries or RPCs inside loops (the N+1 pattern); repeated small file or
socket operations that could be buffered with correct flush semantics; unbounded
whole-file reads; callbacks or network I/O performed while holding unrelated
locks.

**Networking** — a new custom `http.Transport` per request; required response
bodies not read to EOF and closed; pool limits shown by telemetry to be too
small; servers missing workload-appropriate timeouts; network operations with no
deadline or cancellation path.

**Leak shapes** — sub-slices of pooled or large buffers sent to queues or caches;
unbounded in-memory queues; caches without eviction; contexts created without
`defer cancel()`; goroutines started in `init` or constructors.

**Layout** — measured padding in structs allocated at material volume; shared
counters with profiler or hardware evidence of false sharing. Exported, encoded,
reflected, cgo, and `unsafe`-observed layouts are compatibility boundaries.

**Premature optimization** — `sync.Pool` on cold paths; `unsafe` without a
benchmark; hand-rolled versions of stdlib; GC knobs set in code with no recorded
justification. These are findings too: they carry risk and buy nothing.

Also harvest existing `turbo:` markers — deliberate tradeoffs the codebase
already made:

```sh
rg -n '// *turbo:' -g '*.go' .
```

A marker naming a ceiling but no revisit trigger gets flagged `no-trigger`; those
are the ones that quietly become permanent.

## Measurement coverage

A repo that can't measure itself can't defend a change. Report:

- benchmarks: how many, covering which hot paths, which have none;
- `-benchmem` used? `b.Loop()` or a sink, or dead-code-eliminable?
- is there a protected, operable way to capture profiles from the service?
- is PGO evaluated with a representative, current profile where deployment
  stability makes it appropriate?
- is the runtime memory limit set against the real container or host budget,
  with non-Go memory headroom?

Missing representative measurement on the top path usually outranks an individual
speculative allocation finding, because it blocks that fix from being verified.

## Output

Ranked, biggest first, tail cut. Tags are `$go-turbo-review`'s:

```
<n>. <tag> <path>:<line> — <what>
    fix:    <the change>
    weight: hot path | warm | cold
    effort: trivial | moderate | invasive
```

Then:

```
coverage: <N> benchmarks, <M> important paths uncovered. profiles/load tests: <what exists>.
turbo debt: <N> markers, <M> with no revisit trigger.
top 3: <the three things to do first, one line each>
```

Cap the list at roughly 20 findings; beyond that, say so and report the top 20 —
a list nobody finishes is a list nobody starts.

Clean repo: `No structural performance problems found. Benchmark coverage is
<X>; the next move is profiling under real load.`

## Rules

- **Rank ruthlessly.** Three real findings beat forty speculative ones.
- **Distinguish evidence from inference.** Compiler output is evidence of a
  compiler decision, not of its runtime cost. A representative benchmark or
  production measurement is performance evidence. Reading code is inference.
- **Raise paid wins as questions.** Repo-wide you have less context than the
  authors, so pooling and zero-copy come with a suggested measurement rather than
  a demand.
- **Respect deliberate tradeoffs.** A `turbo:` comment means someone already
  thought about it. Check the reasoning holds; leave it otherwise.
- **Say what you didn't cover.** Name the generated code, vendored dependencies,
  and test helpers you skipped.

## Boundaries

Performance only — correctness, security, and style go to their own passes.
Reports, applies nothing. For a diff use `$go-turbo-review`; to act on a finding,
`$go-turbo-analyze` then `$go-turbo-improve`. One-shot, scoped to the current
task.
