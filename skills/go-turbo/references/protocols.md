# Protocol Selection and Framing

Protocol choice fixes semantics long before it changes benchmark numbers.
Start with interoperability, delivery guarantees, security, observability,
and operational ownership. Then measure end-to-end latency, throughput, CPU,
memory, and behavior under loss with realistic message sizes.

## Contents

- [Selection matrix](#selection-matrix)
- [Raw TCP and bounded framing](#raw-tcp-and-bounded-framing)
- [UDP datagrams](#udp-datagrams)
- [HTTP/1.1](#http11)
- [HTTP/2](#http2)
- [HTTP/3](#http3)
- [gRPC unary and streaming calls](#grpc-unary-and-streaming-calls)
- [QUIC transport concepts](#quic-transport-concepts)
- [Flow control and backpressure](#flow-control-and-backpressure)
- [Measurement and correctness gates](#measurement-and-correctness-gates)

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

## Raw TCP and bounded framing

TCP is an ordered byte stream. A `Read` does not correspond to a peer `Write`:
it may return a partial header, combine messages, or split a payload. Define
framing explicitly. A length prefix is simple when the receiver validates the
length before allocating.

```go
package frame

import (
	"encoding/binary"
	"errors"
	"io"
)

const MaxPayload = 1 << 20

var ErrFrameTooLarge = errors.New("frame exceeds maximum payload")

func Read(r io.Reader) ([]byte, error) {
	var header [4]byte
	n, err := io.ReadFull(r, header[:])
	if err != nil {
		// EOF before any header byte is a clean boundary between frames.
		// ReadFull reports a partial header as ErrUnexpectedEOF.
		if n == 0 && errors.Is(err, io.EOF) {
			return nil, io.EOF
		}
		return nil, err
	}
	size := binary.BigEndian.Uint32(header[:])
	if size > MaxPayload {
		return nil, ErrFrameTooLarge
	}
	payload := make([]byte, int(size))
	if _, err := io.ReadFull(r, payload); err != nil {
		// Once a non-empty payload has been advertised, even an EOF before
		// its first byte is a truncated frame rather than a clean shutdown.
		if errors.Is(err, io.EOF) {
			return nil, io.ErrUnexpectedEOF
		}
		return nil, err
	}
	return payload, nil
}

func Write(w io.Writer, payload []byte) error {
	if len(payload) > MaxPayload {
		return ErrFrameTooLarge
	}
	var header [4]byte
	binary.BigEndian.PutUint32(header[:], uint32(len(payload)))
	if err := writeAll(w, header[:]); err != nil {
		return err
	}
	return writeAll(w, payload)
}

func writeAll(w io.Writer, p []byte) error {
	for len(p) != 0 {
		n, err := w.Write(p)
		if err != nil {
			return err
		}
		if n == 0 {
			return io.ErrNoProgress
		}
		p = p[n:]
	}
	return nil
}
```

The example permits an empty payload and caps every non-empty payload at one
application-defined limit. A real protocol should also define version,
message kind, authentication, unknown-field behavior, and whether multiple
frames form one transaction. Check length arithmetic before converting or
adding header sizes.

Set read and write deadlines around protocol phases. A context does not by
itself interrupt an arbitrary `net.Conn` read; arrange cancellation by setting
a deadline or closing the connection. Treat EOF between frames differently
from EOF inside a frame. A truncated frame is a protocol error, not a clean
shutdown.

Buffering helps when the application performs many small operations. It can
hurt when a flush is forgotten or adds latency to an already large write.
Make flush boundaries part of the protocol and measure syscall counts.

## UDP datagrams

UDP preserves datagram boundaries but supplies no delivery, ordering,
deduplication, congestion, or session semantics. A successful write means the
local stack accepted the packet, not that a peer processed it. Design message
IDs, expiry, duplicate handling, authentication, and retry policy when the
application needs them.

Set an application datagram maximum that stays within the deployment path's
effective MTU when possible. IP fragmentation magnifies loss and middlebox
failure. A receive buffer smaller than a datagram can truncate it; choose a
buffer that covers the protocol limit and use APIs that expose truncation when
the platform and implementation allow it. Reject, do not parse, a truncated
message.

Connected UDP narrows the peer and can simplify error delivery, but it does
not become a stream or a reliable connection. For a shared packet socket,
validate source addresses and never let one sender monopolize a single
unbounded processing queue.

Use UDP directly for telemetry or discovery only when occasional loss and
reordering are acceptable by contract. Building reliable transport on UDP is
a protocol project; prefer a reviewed transport rather than growing ad hoc
ACK, retransmission, congestion-control, and crypto layers.

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

## gRPC unary and streaming calls

Unary RPC gives one request and one response with a generated typed contract.
It is usually the clearest default. Set deadlines, maximum message sizes, and
status mappings; a schema does not protect a server from an enormous repeated
field or a client that never finishes sending.

Server streaming fits one request followed by a sequence of results. Client
streaming fits incremental upload or aggregation. Bidirectional streaming is
for truly independent message flows, not merely to avoid repeated unary-call
overhead. Every open stream retains protocol, flow-control, and application
state until completion or cancellation. Goroutine retention depends on the
selected gRPC implementation and handler design; do not assume either zero or
exactly one goroutine per open stream. Confirm it with goroutine and heap
profiles under representative stream counts.

Streaming changes failure semantics. Define whether partial results are
committed, how a client resumes, and whether messages have sequence IDs.
Propagate cancellation to producers, and stop work promptly when a send fails.
Do not assume concurrent sends on one stream are safe unless the selected API
documents it.

Generated message reuse and codec pooling are paid optimizations. They are
unsafe if ownership crosses calls or asynchronous sends retain memory. Profile
allocations, document lifetime, and race-test any reuse.

## QUIC transport concepts

QUIC is an encrypted, multiplexed transport carried over UDP. It integrates
cryptographic handshake state with transport state and can support connection
migration. Streams are ordered within themselves. Missing data on one stream
does not create a transport-ordering requirement for data on another, although
shared connection limits can still reduce both streams' progress.

There are two flow-control budgets: each stream and the connection as a whole.
If the receiver stops consuming, the sender eventually blocks even when the
network is writable. If one application component hoards the connection-level
window, other streams can stall. Bound concurrent streams and bytes in flight,
and keep consuming or cancel streams that are no longer needed.

Zero-round-trip data can reduce setup latency for a resumed relationship, but
it may be replayed. Use it only when the operation's application-level
semantics are inherently replay-safe or idempotent without relying on the
early-data transport to deduplicate it. Anti-replay windows, single-use
tickets, and idempotency keys are defense in depth; they are not permission to
put a non-idempotent mutation in early data. Authentication alone also does
not make a mutation replay-safe. Never place an unconditional charge, grant,
or destructive update in early data.

Loss recovery operates on QUIC packets and retransmittable frame data. One
packet can contain frames for multiple streams as well as connection-control
frames. When loss detection declares that packet lost, data that is still
needed is scheduled in new packets; the original UDP datagram is not replayed
wholesale. Acknowledged or obsolete data need not be sent again. Independent
stream ordering limits the delivery dependency, while the shared congestion
controller and connection flow-control budget can still slow otherwise
unaffected streams.

Connection migration preserves a logical connection across address changes;
it does not guarantee every middlebox accepts the traffic or that application
authorization remains valid for the new path. Log stable connection identity
without treating an IP address as identity.

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
