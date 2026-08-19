# Rate Limiting

A limiter is a policy plus a place to keep state. Choose the algorithm from the
burst behaviour you want, and decide early whether the counter is per-process or
shared — that choice is harder to change than the algorithm.

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
