# Retries and Idempotency

Retries are the mechanism most likely to turn a partial outage into a total one.
Every policy needs an idempotency story, a budget, and jitter.

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
