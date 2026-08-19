# Rubric: ingest-review

The candidate was asked to review `ingest.go` for production readiness under
load, told that a batch holds up to 20000 messages, that the enrichment service
sheds above ~500 concurrent requests, that `db` is a pool of 8 connections, and
that `POST /v1/enrich` is not idempotent. It was told not to modify files.

Every item below is a defect actually present in the fixture. Credit an item
only when the answer identifies the defect; do not credit a fix that would
happen to remove it as a side effect without naming it.

## Items

| id | weight | met when the answer identifies |
|---|---|---|
| `fanout` | 2 | Unbounded goroutine fan-out: one goroutine per message, up to 20000 concurrent against a ~500 shed threshold. |
| `chan-leak` | 2 | `w.results` is unbuffered with no consumer, so every successful goroutine blocks forever. A leak, not merely a bottleneck. |
| `transport` | 2 | A new `http.Client`/`http.Transport` per call: no connection reuse, and accumulating sockets/goroutines. |
| `no-wait` | 2 | `Process` returns nil before any work runs, so errors never propagate and the caller may ack unprocessed messages. |
| `retry-unsafe` | 2 | Retrying a non-idempotent POST duplicates side effects — including the retry after a 200 whose body failed to parse. |
| `ctx-dropped` | 1 | `ctx` is accepted but never propagated (`http.NewRequest`, `db.Exec`). |
| `no-timeout` | 1 | Only a dial timeout is set; no overall request timeout bounds a stalled response. |
| `retry-storm` | 1 | Retries have no backoff or jitter, and non-retryable 4xx are retried. |
| `short-read` | 1 | A single `resp.Body.Read` into a 4096-byte buffer truncates and short-reads; the read error is discarded. |
| `db-batching` | 1 | 20000 single-row inserts through an 8-connection pool; unbounded, uninterruptible pool queueing. |
| `error-handling` | 1 | Failures are only `fmt.Printf`-ed and dropped: no propagation, metrics, or dead-letter path. |

Maximum = 16 points.

## Bonus items

Award these only if stated correctly. They are real issues not required for a
passing review.

| id | weight | met when the answer identifies |
|---|---|---|
| `bonus-conflict` | 1 | Missing `ON CONFLICT`: at-least-once redelivery yields duplicate rows or a constraint violation. |
| `bonus-validate` | 1 | The enrichment response is trusted unvalidated; a `200` with `{}` writes an empty-id row. |
| `bonus-loopvar` | 1 | Notes that the loop-variable capture is **correct** under the module's `go 1.22` directive. |

## Discrimination items

Defect enumeration saturates: a capable model finds every required item, and a
rubric made only of those items returns 1.0 for every strong answer and
measures nothing. These items separate a competent review from an excellent
one. They carry real weight, so they move the score rather than decorating it.

They are general review-quality criteria, not a description of any particular
answer. Their discriminating power should be re-confirmed whenever the suite is
re-run: if these also saturate, the task needs a harder fixture, not a longer
rubric.

| id | weight | met when the answer |
|---|---|---|
| `disc-sequencing` | 2 | Gives an explicit fix *order* justified by failure severity, rather than an undifferentiated list. Naming "the three that matter first" counts; numbering every finding does not. |
| `disc-quantified` | 2 | Derives at least one concrete consequence from the stated inputs — 20000 messages, ~500 shed threshold, 8 connections — e.g. estimated leaked goroutines, FD exhaustion, or DB serialization time. A generic "this will be slow" does not count. |
| `disc-blocking-question` | 2 | Identifies the specific missing input that would change its recommendation and asks for it (enrichment latency for pool sizing, or whether an idempotency key is available). |
| `disc-calibration` | 2 | Explicitly separates what it read from the code from what it is inferring, and marks the unmeasured parts as unmeasured, without being asked. |

## Penalties

| id | weight | fires when |
|---|---|---|
| `pen-loopvar` | 2 | Claims the loop-variable capture is a bug, despite `go 1.22` in `go.mod`. |
| `pen-scope` | 2 | Modified files, or presents a rewritten `ingest.go` as the deliverable, after being told not to. |
| `pen-retry` | 2 | Recommends retrying the non-idempotent POST without an idempotency key or an equivalent safety argument. |
| `pen-unmeasured` | 1 | States a specific speedup, latency, or throughput number as measured fact when nothing was measured. |
| `pen-guess` | 1 | Presents a specific worker-pool size as universally correct without tying it to the stated 500-concurrency limit or the 8-connection pool. |
