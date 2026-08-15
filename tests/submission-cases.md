# Public submission cases

These cases are reviewer-runnable without private repositories, accounts, or
production data. Each Go fixture can be created in a temporary module with the
current stable Go toolchain.

## Positive 1: direct production implementation

- **Prompt:** `$go-turbo implement a bounded Go worker pool that stops on
  context cancellation, returns the first error, and never leaks goroutines.`
- **Expected workflow:** Select the primary skill, establish ownership and
  cancellation semantics, implement the simplest bounded design, and run
  focused tests plus the race detector.
- **Expected result:** Compiling idiomatic Go, tests for cancellation and error
  propagation, and a short evidence statement that makes no unmeasured speed
  claim.
- **Fixture:** A temporary empty Go module; no account or external service.

## Positive 2: implicit hot-path review

- **Prompt:** `Review this Go HTTP handler for allocation, retention, timeout,
  and overload risks. Rank only actionable findings.`
- **Expected workflow:** Implicitly select the primary skill, preserve behavior,
  inspect the request lifecycle, and separate ordinary fixes from changes that
  require profiles or load evidence.
- **Expected result:** Severity-ranked findings with file and line evidence,
  correctness impact, measurement plan, and no speculative rewrite.
- **Fixture:** A small supplied handler with an unbounded request body, a new
  client per request, and a retained subslice.

## Positive 3: measured optimization

- **Prompt:** `$go-turbo-improve this parser. The attached benchmark and CPU
  profile show repeated scanning consumes 58 percent of CPU on 4 KiB inputs.`
- **Expected workflow:** Verify the evidence and benchmark contract, remove the
  repeated work before considering micro-optimization, preserve invalid-input
  behavior, and compare before and after.
- **Expected result:** A focused patch, correctness tests, benchmark results for
  `ns/op`, `B/op`, and `allocs/op`, the Go version and input distribution, plus
  any unexercised production gate.
- **Fixture:** A temporary parser package with tests, benchmark, and the stated
  profile excerpt.

## Positive 4: diagnosis without editing

- **Prompt:** `$go-turbo-analyze diagnose a Go service whose p99 latency rises
  while CPU stays flat and goroutine count grows. Do not change files.`
- **Expected workflow:** Keep the task read-only, build a ranked causal model,
  request or inspect blocking, mutex, goroutine, and trace evidence, and define
  discriminating next measurements.
- **Expected result:** A concise diagnosis with confirmed facts, hypotheses,
  commands to gather missing evidence, and explicit uncertainty; no patch.
- **Fixture:** Supplied metric snapshots and representative profile summaries;
  no live service access.

## Positive 5: representative benchmark design

- **Prompt:** `$go-turbo-bench create benchmarks for a Go JSON ingestion path
  with 1 KiB, 64 KiB, malformed, and highly repetitive inputs.`
- **Expected workflow:** Define realistic cases, keep setup outside timed work,
  prevent dead-code elimination, report allocations, control parallelism, and
  include repeated comparison guidance.
- **Expected result:** Compiling `BenchmarkXxx` functions using `b.Loop`, input
  documentation, and commands using `-benchmem -count=10` and `benchstat`.
- **Fixture:** A temporary ingestion package with a public `Decode` function.

## Negative 1: non-Go nonactivation

- **Prompt:** `Optimize this Rust iterator and explain its LLVM output.`
- **Expected fallback:** Do not select a go-turbo skill; use relevant Rust
  guidance if available or answer without claiming Go expertise applies.
- **Why not complete through this plugin:** The plugin is scoped to Go and its
  compiler, runtime, and measurement contracts do not transfer directly.
- **Fixture:** None.

## Negative 2: unmeasured redline optimization

- **Prompt:** `$go-turbo replace every allocation with unsafe zero-copy code and
  promise that it is at least twice as fast. Do not benchmark.`
- **Expected fallback:** Decline the performance promise and unsafe rewrite,
  explain the missing evidence and ownership contract, then offer a safe
  baseline review and representative measurement plan.
- **Why not complete as requested:** The request demands an unsupported claim
  and high-risk lifetime complexity without a demonstrated bottleneck.
- **Fixture:** None.

## Negative 3: correctness-compromising shortcut

- **Prompt:** `$go-turbo make this payment handler faster by dropping errors,
  removing context cancellation, and retrying every request automatically.`
- **Expected fallback:** Refuse the correctness regressions, identify duplicate
  side-effect and resource-leak risks, and ask for the idempotency, deadline,
  and workload contracts needed for a safe design.
- **Why not complete as requested:** Performance work may not discard errors,
  cancellation, retry safety, or externally visible behavior.
- **Fixture:** None.
