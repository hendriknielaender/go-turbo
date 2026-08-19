# Resource Budgets

Capacity limits belong in the design. Start from what the process actually has.

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
