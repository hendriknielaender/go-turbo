---
name: go-turbo-audit
description: >
  Whole-repository performance audit for Go. Like go-turbo-review but scans
  the entire codebase instead of a diff: a ranked hotlist of allocation
  patterns, heap escapes, unbounded concurrency, missing timeouts, per-item
  I/O, contention risks, and leak-shaped code, plus the repo's benchmark and
  profiling coverage. Use when the user says "audit this codebase for
  performance", "where are the performance problems in this repo", "perf
  audit", "scan for allocations", "is this service going to scale",
  "/go-turbo-audit", or points at a repo and asks what to fix first.
  One-shot report, applies nothing.
license: MIT
---

# go-turbo-audit

`/go-turbo-review`, repo-wide. Same tags, same discipline, wider scope, and
one extra job: assess whether the repo can even tell whether it's fast.

Ranking matters more here than in a diff review. A repo-wide scan surfaces
hundreds of candidates, and a flat list of them is worse than useless — it
buries the three that matter. Rank by expected impact and cut the tail.

## Scope first

Ask, or infer and state, what the repo *is*. A CLI tool, a batch job, and a
request-serving service have different hot paths and almost disjoint
findings. Auditing a CLI for connection pooling wastes everyone's time.

Then find the actual hot paths — HTTP/gRPC handlers, message consumers, the
main processing loop — and weight findings by whether they sit on one. A
finding in `cmd/migrate` is not equal to a finding in the request path.

## Scan

Compiler and tooling first — they're fast and they're evidence:

```sh
go vet ./...
go build -gcflags=-m ./... 2>&1 | grep -E 'escapes to heap|moved to heap'
go test -bench=. -benchmem -run=^$ ./... 2>&1     # existing benchmarks
```

If `golangci-lint` is available, the `prealloc`, `fieldalignment`, and
`bodyclose` analyzers each map directly to findings here.

Then read for the patterns that static analysis misses:

**Allocation** — `append` into a nil slice where the length is known;
`make` without capacity; `+=` string building in loops; `[]byte`↔`string`
round trips; `fmt.Sprintf` on hot paths; per-iteration allocation that could
be hoisted; regexps or templates compiled per call.

**Concurrency** — `go` statements over unbounded input; goroutines with no
exit path; channels used as hot-path queues; a single mutex over a structure
touched by everything; `sync.Map` used as a general-purpose map;
`sync.RWMutex` guarding very short critical sections.

**I/O** — queries or RPCs inside loops (the N+1 pattern); unbuffered file and
socket writes; `io.Copy` per request without a pooled buffer; `os.ReadFile`
on files that could be large.

**Networking** — `http.Client` constructed per request; response bodies
closed but not drained; default `MaxIdleConnsPerHost` (2) on a
high-concurrency client; `http.Server` with no `ReadHeaderTimeout`; network
reads with no deadline.

**Leak shapes** — sub-slices of pooled or large buffers sent to queues or
caches; unbounded in-memory queues, caches without eviction; contexts created
without `defer cancel()`; goroutines started in `init` or constructors.

**Layout** — badly ordered fields in structs allocated in bulk; atomic
counters adjacent in a struct written by different goroutines.

**Premature optimization** — `sync.Pool` on cold paths; `unsafe` without a
benchmark; hand-rolled versions of stdlib; GC knobs set in code with no
recorded justification. These are findings too: they carry risk and buy
nothing.

Also harvest existing `turbo:` markers — deliberate tradeoffs the codebase
already made:

```sh
grep -rn '// *turbo:' --include='*.go' .
```

Any marker naming a ceiling but no revisit trigger gets flagged
`no-trigger`; those are the ones that quietly become permanent.

## Measurement coverage

A repo that can't measure itself can't defend a change. Report:

- benchmarks: how many, covering which hot paths, which have none
- `-benchmem` used? `b.Loop()` or a sink, or dead-code-eliminable?
- is `net/http/pprof` exposed in the service binary?
- is there a `default.pgo`? (PGO is typically a few percent for near-zero
  effort — its absence is a standing finding for any service)
- `GOMEMLIMIT` set in the container config?

Missing benchmark coverage on the top hot path usually outranks any
individual allocation finding, because it blocks every fix below it from
being verified.

## Output

Ranked, biggest first, tail cut:

```
<n>. <tag> <path>:<line> — <what>
    fix:    <the change>
    weight: hot path | warm | cold
    effort: trivial | moderate | invasive
```

Tags are `/go-turbo-review`'s: `alloc:`, `escape:`, `algo:`, `sync:`, `io:`,
`net:`, `leak:`, `premature:`, `layout:`.

Then:

```
coverage: <N> benchmarks, <M> hot paths uncovered. pprof: <yes|no>. PGO: <yes|no>.
turbo debt: <N> markers, <M> with no revisit trigger.
top 3: <the three things to do first, one line each>
```

Cap the list at roughly 20 findings. If there are more, say so and report the
top 20 — a list nobody finishes is a list nobody starts.

Clean repo: `No structural performance problems found. Benchmark coverage is
<X>; the next move is profiling under real load.`

## Rules

- **Rank ruthlessly.** Three real findings beat forty speculative ones.
- **Distinguish evidence from inference.** Compiler output and existing
  benchmark numbers are evidence. Reading code is inference. Label each
  finding accordingly.
- **Don't demand paid wins.** Repo-wide, you have less context than the
  authors. Raise pooling and zero-copy as questions with a suggested
  measurement, not as requirements.
- **Respect deliberate tradeoffs.** A `turbo:` comment means someone already
  thought about it. Check the reasoning; don't re-litigate it by default.
- **Say what you didn't cover.** Generated code, vendored dependencies, and
  test helpers are usually out of scope — name them.

## Boundaries

Performance only — correctness, security, and style go to their own passes.
Reports, applies nothing. One-shot.

For a diff, use `/go-turbo-review`. To act on a finding, `/go-turbo-analyze`
then `/go-turbo-improve`.

"stop go-turbo-audit" or "normal mode" to revert.
