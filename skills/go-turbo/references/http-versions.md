# HTTP/1.1, HTTP/2, and HTTP/3

What actually differs between the versions: multiplexing, head-of-line
behaviour, and the connection model each one implies.

## HTTP/1.1

HTTP/1.1 is often the operational baseline: intermediaries understand it,
traces are readable, and request/response boundaries are explicit. Persistent
connections avoid repeated handshake cost. Under concurrent load, clients
usually need a pool because one connection cannot freely multiplex unrelated
responses without ordering constraints.

Always consume or deliberately abandon response bodies according to the
client transport's reuse contract, then close them. Bound request headers and
bodies, set phase-appropriate timeouts, and cap connections per upstream.
Pipelining is not a general answer to head-of-line blocking; do not assume it
is supported across clients and intermediaries.

HTTP semantics matter more than codec speed: safe and idempotent methods,
cache rules, conditional requests, status codes, and retry headers allow
infrastructure to behave correctly. Do not smuggle retryable mutations behind
a method merely because a load balancer treats it favorably.

## HTTP/2

HTTP/2 multiplexes streams over a connection and compresses repeated header
metadata. It is a strong fit for many concurrent requests to one origin,
especially when connection setup is expensive. Multiplexing reduces the need
for a large connection pool, but one connection can still be a capacity and
failure boundary.

Stream concurrency, connection and stream flow-control windows, peer limits,
and long-running responses all affect fairness. More streams do not create
more downstream capacity. Because the transport is TCP, a lost segment delays
delivery of later bytes for every stream on that connection even though HTTP
frames are logically independent.

Keep connections reused, bound each body, propagate cancellation, and test
behavior when the peer lowers its stream limit. Opening extra connections may
improve isolation in a measured case, but it also adds handshakes, memory, and
load-balancer state.

## HTTP/3

HTTP/3 maps HTTP semantics onto QUIC rather than TCP. Stream ordering means a
missing byte range on one stream does not itself impose an ordering dependency
on another stream. A QUIC packet can still carry frames from several streams,
and congestion control plus connection-level flow control remain shared. Thus
avoiding cross-stream transport ordering is not the same as eliminating
cross-stream interference.

The fit depends on network loss, mobility, handshake reuse, UDP reachability,
proxy support, and fallback behavior. Test through the real CDN, load balancer,
firewall, and client population. Preserve HTTP semantics across HTTP versions;
an endpoint must not become less safe when negotiated over a different
transport.

Avoid claims tied to one package release. Confirm the chosen implementation's
current support, defaults, limits, observability hooks, and cancellation rules
from its primary documentation and integration tests. When an HTTP/3 or QUIC
API requires a particular Go or library release, record that minimum and test
the negotiated fallback, normally HTTP/2 or HTTP/1.1. Do not silently make an
otherwise compatible request fail because the preferred transport is absent.
