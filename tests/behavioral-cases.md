# Behavioral acceptance cases

Run these cases with a fresh agent after changing the primary skill. Give the
agent only the user prompt and the path to `skills/go-turbo/SKILL.md`; do not
describe the desired answer. Record which references it chose to load.

The cases test judgment, not exact prose. A response fails when it claims an
unmeasured speedup, adds avoidable complexity, weakens correctness, ignores the
repository's Go version, or loads the whole knowledge base without a reason.

## 1. Idiomatic implementation under a wide input range

Prompt: implement stable deduplication for trusted `[]uint64`; nil must remain
nil, normal inputs contain 8–50 values, and occasional inputs reach one million.
No benchmark or profile is available.

Pass when the agent chooses an expected-linear, readable implementation,
preserves nil semantics, states the memory/preallocation tradeoff, and labels
performance as unmeasured. Fail for quadratic scaling, pooling, unsafe code, or
a fabricated benchmark result.

## 2. Restraint on a cold startup path

Prompt: a config loader runs once, logs about 2 ms, and has no benchmark. Ask to
add `sync.Pool`, `unsafe.String`, pointer-everywhere APIs, universal field
reordering, and a process-wide `GOGC` increase.

Pass when the agent rejects those changes pending a startup objective and
representative evidence, explains each risk accurately, and proposes the
smallest useful measurement. Fail when user enthusiasm is treated as evidence.

## 3. Diagnosis does not silently become implementation

Prompt: ask why a Go service has poor p99 latency, supplying only CPU and error
rate metrics and explicitly requesting diagnosis, not a fix.

Pass when the agent preserves read-only scope, identifies missing queue/wait
evidence, selects profiles or trace appropriate to the question, and labels
code-reading ideas as hypotheses. Fail when it edits files or equates low CPU
with mutex blocking alone.

## 4. Cancellation and bounded concurrency

Prompt: review a loop that launches one goroutine per message, sends results to
an unbounded queue, and performs a database call that ignores context.

Pass when the agent derives concurrency from the scarce dependency, makes
admission/queue outcomes explicit, propagates cancellation at every wait, and
requires race and overload tests. Fail for a guessed worker count presented as
universal or for a channel/pointer ownership race.

## 5. HTTP lifecycle and retry safety

Prompt: review code that creates a custom transport per request, reads only a
prefix of an unbounded response, retries a mutating POST at several layers, and
has no request deadline.

Pass when the agent separates client from transport reuse, refuses an unbounded
drain, requires a finite end-to-end retry budget and replay-safe semantics, and
adds phase/workload-appropriate deadlines. Fail for “always drain,” “clients
never share pools,” or automatic retries of an ambiguous mutation.

## 6. Toolchain comparison

Prompt: decide whether to upgrade a service between two exact Go releases on
Linux AMD64 and ARM64 while the developer is working on macOS.

Pass when both exact toolchain binaries run the same compatible benchmark
source, raw samples and metadata are preserved, native deployment architectures
are tested, results are compared statistically, and canary/rollback gates stay
open. Fail when author-machine numbers or one benchmark sample become a release
claim.

## Completion contract

A release candidate passes only when all structural and snippet validators are
green, the forbidden-provenance scan is empty, and fresh agents pass cases 1–6
without being shown these criteria. Record any unexercised platform or
production gate instead of calling it proven.
