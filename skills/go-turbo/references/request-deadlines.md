# Timeouts, Cancellation, and Retries

Every wait needs a bound and every retry needs a budget. An unbounded call and
an unbudgeted retry are the two mechanisms that turn a slow dependency into an
outage of your own.

Bound each phase according to what it means:

- `net.Dialer.Timeout` bounds connection establishment.
- `TLSHandshakeTimeout` bounds TLS negotiation.
- `ResponseHeaderTimeout` starts after the request, including its body, has
  been written and bounds the wait for response headers. It does not bound
  reading the response body.
- a request context bounds and cancels the logical operation.
- `http.Client.Timeout` bounds the complete exchange, including redirects and
  reading the body.

`Client.Timeout` is a useful backstop for bounded request/response calls. It is
usually wrong for an intentionally long stream because the deadline does not
reset when data arrives. For streams, use a startup deadline plus
protocol-level idle heartbeats or resettable read/write deadlines where the
connection API permits them. Keep an overall business deadline only when the
stream itself has a finite lifetime.

Server and client phase timeouts do not replace context propagation. Pass the
request context through database, RPC, queue, and channel operations. A timeout
that returns to the caller while work continues merely converts latency into
hidden load.

Retries require a separate, finite budget. Retry only operations whose effects
are safe to repeat, only when request bodies are replayable, and with backoff,
jitter, and respect for server guidance. `http.Transport` performs a narrow set
of retries for reused-connection network failures and requests it recognizes as
idempotent; do not assume it implements the application's recovery policy.
Attempt limits, circuit breaking, hedging, and load shedding belong to the
`retries.md` reference, routed from the primary skill.
