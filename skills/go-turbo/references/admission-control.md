# Admission Control

Decide what to accept before the queue does it for you.

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
