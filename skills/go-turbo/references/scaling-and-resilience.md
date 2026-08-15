# Scaling, Backpressure, and Resilience

An overloaded service is already in a failure mode. The engineering goal is
to keep that failure bounded, observable, and recoverable while preserving the
most important work. Capacity limits belong in the design, not in an emergency
configuration added after queues consume the machine.

## Contents

- [Start with resource budgets](#start-with-resource-budgets)
- [Admission control](#admission-control)
- [Rate limiting](#rate-limiting)
- [Fixed bounded queues](#fixed-bounded-queues)
- [Circuit-breaker semantics](#circuit-breaker-semantics)
- [Passive and active load shedding](#passive-and-active-load-shedding)
- [Retries, idempotency, and jitter](#retries-idempotency-and-jitter)
- [HTTP overload responses](#http-overload-responses)
- [Degraded modes](#degraded-modes)
- [Ten-thousand-plus connections](#ten-thousand-plus-connections)
- [Accept loops and operating-system tuning](#accept-loops-and-operating-system-tuning)
- [Validation](#validation)

## Start with resource budgets

Derive concurrency from the tightest resource, not a round number. For each
request or connection, estimate CPU time, live Go heap, kernel socket memory,
open descriptors, downstream concurrency, queued bytes, and deadline. Measure
the estimate under representative load and retain headroom for recovery,
background work, logs, health checks, and deployments.

Little's Law is a useful consistency check: average concurrency equals arrival
rate multiplied by average time in the system when the system is stable. It
does not promise stability during bursts or heavy-tailed latency. Use high
percentile service time and explicit burst capacity for admission decisions.

Every limit needs a policy:

- what is counted and when the reservation begins;
- which callers or priorities share it;
- whether excess work rejects, waits, or degrades;
- how cancellation and panic release the reservation;
- which metric proves saturation rather than merely failure.

## Admission control

Acquire capacity before allocating large request state or calling a scarce
dependency. A semaphore is effective when one request consumes roughly one
unit. Weighted resources need weighted admission or separate limits so one
large request cannot masquerade as one tiny request.

```go
package admission

import (
	"context"
	"errors"
)

var ErrOverloaded = errors.New("service capacity exhausted")

type Limiter struct {
	inflight chan struct{}
}

func New(maxInflight int) *Limiter {
	if maxInflight <= 0 {
		panic("maxInflight must be positive")
	}
	return &Limiter{inflight: make(chan struct{}, maxInflight)}
}

// Do rejects immediately when no slot is available. It does not promise
// fairness between callers.
func (l *Limiter) Do(ctx context.Context, fn func(context.Context) error) error {
	// A select may choose the send when both the slot and a canceled context
	// are ready. Check cancellation on both sides of the acquisition to avoid
	// entering fn when cancellation is already observable. Cancellation can
	// still race the final check; fn must honor its context.
	if err := ctx.Err(); err != nil {
		return err
	}
	select {
	case l.inflight <- struct{}{}:
	case <-ctx.Done():
		return ctx.Err()
	default:
		return ErrOverloaded
	}
	select {
	case <-ctx.Done():
		<-l.inflight
		return ctx.Err()
	default:
	}
	defer func() { <-l.inflight }()
	return fn(ctx)
}
```

Immediate rejection is appropriate when waiting would consume the client's
deadline without increasing throughput. A short bounded wait can smooth tiny
bursts, but include it in end-to-end latency and abandon it on cancellation.
Do not dynamically raise a limit merely because a queue is full; that defeats
the protection precisely when the dependency is slow.

Partition limits only when isolation justifies unused capacity. Per-tenant
limits stop one caller from monopolizing the service; a small shared reserve
can preserve utilization. Validate priority inversion and starvation under
load rather than assuming channel scheduling is fair.

## Rate limiting

Concurrency admission bounds simultaneous work; a rate limiter bounds starts
or consumed units over time. They protect different failure modes and are
often both necessary. A low request rate can still exhaust concurrency when
requests are slow, while a short high-rate burst can overload a dependency
without exceeding a steady-state concurrency target.

Choose semantics from the workload:

- A **token bucket** refills at an average rate and permits a configured burst.
  Charge tokens by the protected cost when requests vary materially; counting
  every request as one otherwise lets expensive calls consume disproportionate
  capacity. Set burst from the downstream's measured burst tolerance, not from
  the rate multiplied by an arbitrary window.
- A **leaky bucket** or virtual-scheduling limiter smooths departures toward a
  fixed cadence. If it queues rather than rejects, cap both queue length and
  maximum wait so the limiter cannot turn overload into unbounded latency.

Refill lazily from elapsed monotonic time when checking or reserving capacity.
Do not allocate one ticker or goroutine per client. Clamp the balance to the
burst limit, handle long idle intervals without overflow, and inject a clock
for deterministic tests. A delayed reservation must abandon its wait promptly
when its context is canceled. Define whether a reservation consumes capacity
at admission or at execution; never silently leak a token when cancellation
happens before the documented consumption point.

Per-tenant limiting also needs a bound on limiter state. Use a capped table,
sharded if contention is measured, and evict only entries that are idle and
have no outstanding reservation. Deleting an active tenant's state restores a
fresh burst and is an abuse vector. Define what happens at the table cap: use a
coarser shared limiter, reject new identities, or evict a verified idle entry.
Do not accept attacker-chosen identity strings into an unbounded map or expose
one metric label per tenant.

A process-local limiter cannot enforce a fleet-wide quota. Either allocate
explicit per-instance shares with headroom for uneven routing, or use a
distributed authority whose consistency, outage behavior, and latency are
part of the service contract. Decide whether authority failure fails open,
fails closed, or falls back to a smaller local allowance; test that mode rather
than discovering it during an incident.

On rejection, return a machine-readable reason and a meaningful retry time
when one can be estimated. For HTTP, caller-specific limits normally use 429;
`Retry-After` is a lower-bound hint, not permission to retry outside the
caller's total budget, and clients should still add jitter. Export admitted and
rejected units, wait duration, active limiter entries, eviction count, burst
utilization, and authority errors with bounded-cardinality labels.

Test initial burst, steady refill, long idle clamping, fractional rates,
concurrent callers, cancellation before and during a wait, table-cap behavior,
idle eviction, clock movement as supported by the chosen clock, and distributed
authority loss. Load-test the rate and concurrency controls together: either
control tested alone can hide the other's bottleneck.

## Fixed bounded queues

A queue absorbs a finite mismatch between arrival and service rates. It cannot
fix sustained overload. Capacity must be fixed from a memory and latency
budget: queued work times worst-case retained bytes must fit, and queue wait
must leave enough deadline to execute.

A buffered channel is a useful bounded queue. Its capacity counts waiting
items only; active workers are additional concurrency. Keep one owner for
closing, never close from competing producers, and decide explicitly whether
submission blocks, times out, or rejects.

```go
package workqueue

import (
	"context"
	"errors"
)

var ErrFull = errors.New("work queue is full")

type Queue[T any] struct {
	items chan T
}

func New[T any](capacity int) *Queue[T] {
	if capacity <= 0 {
		panic("queue capacity must be positive")
	}
	return &Queue[T]{items: make(chan T, capacity)}
}

func (q *Queue[T]) TrySubmit(value T) error {
	select {
	case q.items <- value:
		return nil
	default:
		return ErrFull
	}
}

func (q *Queue[T]) Receive(ctx context.Context) (T, error) {
	// Do not consume an item when shutdown was already requested at entry.
	if err := ctx.Err(); err != nil {
		var zero T
		return zero, err
	}
	select {
	case value := <-q.items:
		return value, nil
	case <-ctx.Done():
		var zero T
		return zero, ctx.Err()
	}
}
```

This example intentionally has no `Close`; lifecycle ownership differs by
service, and receiving from a closed channel without checking the second
result would fabricate zero-value work forever. Production shutdown must stop
admission, drain or cancel according to contract, then stop workers.

`Receive` gives cancellation priority only when the context is already done at
entry. If an item and cancellation become ready together after that check, Go
may select either. A returned item has transferred to the caller and must be
processed or explicitly discarded under the shutdown policy; the method does
not silently dequeue and return cancellation. Services requiring a strict
drain boundary should stop producers first and have the queue owner close a
separate admission state before canceling workers.

Queue metrics need capacity, depth, oldest-item age, rejection count, and time
spent waiting. Depth alone misses a small queue whose oldest item already
exceeded its deadline. Drop expired work before execution and make that outcome
visible.

## Circuit-breaker semantics

Use a maintained, tested circuit-breaker implementation when a breaker is
warranted. A plausible-looking bespoke breaker often races transitions,
admits too many probes, counts caller cancellations as dependency failures, or
flaps on sparse traffic. Configure and test these state semantics explicitly:

- **Closed:** requests pass. Only eligible dependency outcomes enter a rolling
  failure calculation, and a minimum sample volume prevents one failure from
  opening a quiet service.
- **Open:** requests fail fast until a monotonic-time recovery interval ends.
  The open result should be distinguishable from an attempted call.
- **Half-open:** a strictly bounded number of probes enter. Sufficient success
  closes the breaker; an eligible failure reopens it. All other calls reject.

One authority must perform each transition. Reset rolling state deliberately
on transitions, and define how concurrent completions from the previous state
are classified. Timeouts, transport failures, overload responses, application
errors, caller cancellation, and validation failures are different signals;
count only outcomes that indicate the protected dependency is unhealthy.

A breaker is not a concurrency limit. Requests admitted just before opening
can still pile up, and a healthy but saturated dependency can time out without
failing quickly. Pair the breaker with deadlines, admission control, and a
retry budget. Test state transitions with a controllable clock and concurrent
probes, then load-test recovery without a synchronized stampede.

## Passive and active load shedding

Passive shedding lets an existing bound apply backpressure: a full queue
rejects, a semaphore declines admission, or a deadline expires. It is simple
and tied directly to a resource, but may react only after latency is already
high.

Active shedding rejects earlier using signals such as inflight work, queue
age, CPU saturation, dependency latency, or a concurrency controller. Use a
signal causally related to capacity. Process-wide CPU can be misleading when
the real bottleneck is one database pool; error rate can rise because shedding
already works.

Add hysteresis: enter shedding at a high watermark sustained for a short
window, and exit only below a lower watermark for a recovery window. Separate
thresholds prevent rapid on/off oscillation. Rate-limit state-change logs and
export current mode, trigger, duration, and rejection reason.

Never make readiness fail merely because the instance is shedding ordinary
load unless removal is the intended recovery. Ejecting every overloaded
instance transfers its traffic to the remainder and can collapse the fleet.

## Retries, idempotency, and jitter

A retry multiplies load at the moment a dependency has least capacity. Retry
only transient outcomes, only while enough deadline remains, and only when the
operation is idempotent or carries a server-enforced idempotency key. "The
client did not receive a response" does not mean the mutation did not happen.

Use a total attempt cap and a total elapsed-time budget. Back off between
attempts and add jitter so clients do not synchronize. Honor a valid server
retry hint when it fits within the caller's remaining budget. Place retries at
one layer; stacked SDK, proxy, and application retries multiply unexpectedly.

```go
package retry

import (
	"context"
	"errors"
	"time"
)

var ErrUnsafeRetry = errors.New("retry requires a stable idempotency key")

type Jitter func(upper time.Duration) time.Duration

func Do(
	ctx context.Context,
	maxAttempts int,
	totalBudget time.Duration,
	baseDelay time.Duration,
	maxDelay time.Duration,
	idempotencyKey string,
	retryable func(error) bool,
	jitter Jitter,
	op func(context.Context, string) error,
) error {
	if maxAttempts < 1 {
		return errors.New("maxAttempts must be positive")
	}
	if totalBudget <= 0 {
		return errors.New("totalBudget must be positive")
	}
	if baseDelay < 0 || maxDelay < baseDelay {
		return errors.New("invalid retry delay bounds")
	}
	if op == nil || retryable == nil {
		return errors.New("retry callbacks must not be nil")
	}
	if maxAttempts > 1 {
		if idempotencyKey == "" {
			return ErrUnsafeRetry
		}
		if baseDelay <= 0 {
			return errors.New("baseDelay must be positive when retrying")
		}
		if jitter == nil {
			return errors.New("jitter must not be nil when retrying")
		}
	}

	budgetCtx, cancel := context.WithTimeout(ctx, totalBudget)
	defer cancel()

	delay := baseDelay
	var last error
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		if err := budgetCtx.Err(); err != nil {
			return err
		}
		last = op(budgetCtx, idempotencyKey)
		if last == nil {
			return nil
		}
		if err := budgetCtx.Err(); err != nil {
			return err
		}
		if !retryable(last) || attempt == maxAttempts {
			return last
		}
		wait := jitter(delay)
		if wait < 0 || wait > delay {
			return errors.New("jitter returned a duration outside [0, delay]")
		}
		timer := time.NewTimer(wait)
		select {
		case <-timer.C:
		case <-budgetCtx.Done():
			if !timer.Stop() {
				select {
				case <-timer.C:
				default:
				}
			}
			return budgetCtx.Err()
		}
		if delay < maxDelay {
			if delay > maxDelay/2 {
				delay = maxDelay
			} else {
				delay *= 2
			}
		}
	}
	return last
}
```

`totalBudget` establishes an overall timeout; an earlier parent deadline still
wins. The operation must honor its context and use transport or database
deadlines, because a callback that ignores cancellation cannot be forcibly
stopped by the wrapper. Keep `maxDelay` below the request's useful remaining
lifetime. The retry classifier should be protocol-specific.

The same `idempotencyKey` is passed to every attempt. For a mutation, the
server must atomically store that key and the committed result with the state
change in durable storage, then return the same result to concurrent or later
duplicates. A check followed by a separate write is not sufficient: two
attempts can both pass the check. Retain deduplication records at least through
the maximum retry and replay horizon, bind a key to the authenticated caller
and operation, and reject reuse with different input. Naturally idempotent
reads may use a distinct wrapper whose contract makes that property explicit;
do not fake a key without server enforcement.

These examples use `ctx.Err()` for broad toolchain compatibility. Go 1.20 and
newer can return `context.Cause(ctx)` when the application needs the
cancellation cause. The injected jitter callback keeps the wrapper independent
of a random-number API and makes tests deterministic. Go 1.22 and newer can
implement full jitter with the package-level `math/rand/v2` functions. On an
older toolchain, use `math/rand` with an explicitly considered seeding policy;
an individual `rand.Rand` is not safe to share between goroutines without
synchronization.

Do not retry malformed requests, authorization failures, or local admission
rejections against the same saturated instance without a changed condition.

## HTTP overload responses

Use `503 Service Unavailable` when temporary capacity prevents service. Include
`Retry-After` only when the server has a meaningful estimate; the value is an
HTTP date or integer seconds. Clients still need jitter and a budget.

```go
package overload

import (
	"net/http"
	"strconv"
	"time"
)

func Reject(w http.ResponseWriter, retryAfter time.Duration) {
	if retryAfter > 0 {
		seconds := int64(retryAfter / time.Second)
		if retryAfter%time.Second != 0 {
			seconds++
		}
		if seconds < 1 {
			seconds = 1
		}
		w.Header().Set("Retry-After", strconv.FormatInt(seconds, 10))
	}
	http.Error(w, "temporarily unavailable", http.StatusServiceUnavailable)
}
```

Use `429 Too Many Requests` for a caller-specific rate limit when that is the
actual condition. Emit a low-cardinality machine-readable reason in headers or
the response schema without exposing internal capacity details.

## Degraded modes

A degraded mode should preserve a named invariant, not return plausible but
wrong data. Examples include serving a bounded-age cache, omitting optional
enrichment, accepting a durable command for later processing, or switching an
expensive exact result to a documented approximation.

Define activation, maximum staleness, authorization behavior, user-visible
signal, and exit criteria. Never bypass security checks, accounting, or durable
write requirements as a performance fallback. Exercise degraded behavior in
tests and drills; code reached only during an incident is otherwise untested
production code.

## Ten-thousand-plus connections

Large connection counts are a budget exercise, not a special Go mode. Account
for at least:

- **File descriptors:** listeners, accepted and outbound sockets, files,
  pipes, logs, and monitoring endpoints. Reserve headroom for reconnects and
  deployments rather than setting the process limit equal to target clients.
- **Memory:** goroutine stacks, connection structs, TLS and codec state,
  application read/write buffers, queued messages, and kernel socket buffers.
  Multiply measured per-connection live memory by the target plus headroom.
- **Ports and state tables:** outbound connections consume source-port and NAT
  state. Limits depend on the full address tuple, reuse, destination mix, and
  network devices; inbound accepted sockets do not consume local ephemeral
  ports in the same way.
- **Scheduler and CPU:** mostly idle sockets are different from thousands of
  simultaneously runnable handlers. Benchmark burst wakeups and broadcast
  patterns, not just an idle steady state.
- **Backlog and accept rate:** handshake queues and accepted-but-unhandled
  connections are finite. A larger backlog cannot repair a handler that never
  catches up.

Avoid per-connection timers, ticker goroutines, and fixed large buffers unless
measurements justify them. Deadlines integrated with the runtime are usually
cheaper and clearer. Bound outbound queues per connection so one slow client
cannot retain arbitrary messages. Sample high-cardinality connection details
rather than labeling metrics by peer.

## Accept loops and operating-system tuning

A raw accept loop must not spin on repeated errors. On shutdown, return. On a
resource-exhaustion or transient failure, log with rate limiting and retry with
a bounded exponential delay that resets after a successful accept. Continuing
immediately can consume a CPU while the descriptor shortage prevents recovery.

Operating-system limits, backlog semantics, socket-buffer accounting, and
network-stack controls vary by kernel, container runtime, and cloud platform.
Never paste system-control values as universal tuning. Record the observed
default and effective value on the deployment host, change one constraint at a
time, load-test it, and document rollback. Some settings belong to the host or
orchestrator and cannot be changed meaningfully inside a container.

Raising descriptor or backlog limits without bounding application memory and
work merely moves the crash. Verify graceful close, half-open peers, keepalive
policy, load-balancer idle timeouts, and restart waves at the target scale.

## Validation

Run an overload test that crosses capacity gradually, holds above it, then
returns below it. A healthy design shows bounded memory and queue age, prompt
rejection, useful retry hints, continued priority traffic, and recovery without
a retry storm.

Also test cancellation at every waiting point, dependency slowness without
errors, synchronized client retries, process restart, and one tenant flooding
the service. Run the race detector for limiter, queue, breaker integration, or
shutdown changes. Report throughput together with tail latency, rejection
rate, inflight work, queue age, and resource ceilings.

If limits have not been measured in the deployment environment, state that
open gate rather than presenting a connection count as proven capacity.
