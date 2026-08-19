# Protocol Selection

Choose the highest-level protocol the contract allows, then verify it under the
real message shape.

## Selection matrix

| Choice | Strong fit | Cost or constraint |
| --- | --- | --- |
| Raw TCP | A small internal protocol with strict control of both endpoints | You own framing, evolution, security integration, limits, and tooling |
| UDP | Loss-tolerant datagrams or a protocol that implements its own reliability | Packets may be lost, duplicated, reordered, or fragmented |
| HTTP/1.1 | Broad compatibility, simple request/response, mature tooling | Limited multiplexing; connection count grows with concurrency |
| HTTP/2 | Many concurrent streams and compact repeated headers | All streams share one ordered TCP transport and connection-level limits |
| HTTP/3 | Multiplexing where transport loss between streams matters | UDP reachability, QUIC operations, and different observability assumptions |
| gRPC | Typed service contracts, generated clients, unary and streaming RPC | Schema and RPC ecosystem commitment; message and stream limits still required |

No row is universally fastest. A custom binary protocol can lose to HTTP when
its deployment, retries, logging, or connection management are immature. An
HTTP/3 path can lose on a clean nearby network where setup and encryption
dominate. Select on the production path, not loopback alone.

## Flow control and backpressure

Transport flow control protects receiver memory; it does not protect database,
CPU, or downstream capacity. Add application admission control above every
protocol. A bounded queue should reject or time out explicitly when full,
rather than accumulating messages behind a stream window.

Read loops create pressure when they decode faster than workers can finish.
Write loops create pressure when peers consume slowly. Bound both directions,
avoid one goroutine per queued message, and include buffered bytes in memory
budgets. Cancellation must release reservations and unblock waiters.

## Measurement and correctness gates

Compare protocols with the same logical operation and security level. Include:

- cold and reused connections;
- realistic request and response size distributions;
- concurrency below, at, and above the service capacity;
- clean networks plus representative latency, loss, and reordering;
- CPU, allocations, resident memory, open connections, and bytes on the wire;
- cancellation, slow readers, truncated messages, and peer restarts.

Loopback throughput is a codec and scheduler test, not an Internet result.
Validate fallbacks and intermediary behavior in the deployment environment.
Keep the most conventional protocol when a specialized choice does not deliver
a stable, operationally meaningful improvement.
