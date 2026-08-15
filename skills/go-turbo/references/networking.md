# Networking

Network performance is mostly lifecycle management: reuse established
connections, bound every wait and queue, control concurrency at the dependency,
and account for each connection until it closes. Tune socket details only after
the protocol and application boundaries are measured.

## Contents

- [Choose the highest useful abstraction](#choose-the-highest-useful-abstraction)
- [Reuse HTTP connections](#reuse-http-connections)
- [Configure and share clients deliberately](#configure-and-share-clients-deliberately)
- [Timeouts, cancellation, and retries](#timeouts-cancellation-and-retries)
- [HTTP servers](#http-servers)
- [HTTP/2](#http2)
- [TLS](#tls)
- [DNS](#dns)
- [Socket and operating-system controls](#socket-and-operating-system-controls)
- [Long-lived and high-count connections](#long-lived-and-high-count-connections)
- [Connection lifecycle observability](#connection-lifecycle-observability)
- [Profile under network-shaped load](#profile-under-network-shaped-load)
- [Version compatibility](#version-compatibility)

## Choose the highest useful abstraction

Start with `net/http` when the contract is HTTP. It provides connection reuse,
proxy support, TLS integration, cancellation, and HTTP/2. Drop to `net.Conn`
only when a measured requirement needs a custom stream protocol or precise
connection control. That choice also makes framing, limits, negotiation,
compatibility, and observability application responsibilities.

UDP removes stream ordering and connection setup but also removes reliable
delivery, congestion behavior, and flow control from the application-facing
contract. QUIC restores reliable multiplexed streams over UDP with different
loss and migration behavior. gRPC adds schemas and streaming semantics over
HTTP/2. Compare payload, latency, interoperability, and failure behavior—not
only a loopback throughput number. Use the
[protocol guide](protocols.md) for the decision matrix.

## Reuse HTTP connections

`http.Transport` caches connections and is safe for concurrent use. Reusing a
TCP/TLS connection avoids dialing and handshaking, reduces port churn, and is
normally the largest client-side win.

Always close a successful response body. For HTTP/1, reading it to EOF before
close lets the transport reuse the connection. Drain only when the accepted
body size is already bounded; otherwise enforce a limit and give up reuse when
the peer exceeds it:

```go
var ErrResponseTooLarge = errors.New("response exceeds discard limit")

func discardResponseWithinLimit(
	resp *http.Response,
	maxBytes int64,
) (retErr error) {
	if maxBytes < 0 || maxBytes == math.MaxInt64 {
		return errors.New("maxBytes must be in [0, math.MaxInt64)")
	}
	defer func() {
		retErr = errors.Join(retErr, resp.Body.Close())
	}()

	limited := &io.LimitedReader{R: resp.Body, N: maxBytes + 1}
	if _, err := io.Copy(io.Discard, limited); err != nil {
		return err
	}
	if limited.N == 0 {
		// The body was at least maxBytes+1 bytes. Close without reading more;
		// the HTTP/1 connection may not be reusable.
		return ErrResponseTooLarge
	}
	return nil // EOF reached within the accepted bound.
}
```

Do not read an attacker-controlled or unexpectedly huge body merely to save a
connection. A server may send exactly `maxBytes+1` bytes or never finish; the
sentinel read detects the former, while the request context or body-read
deadline must bound the latter. If a body is larger than the useful drain
limit, close it and accept that the HTTP/1 connection may not be reused.
Connection reuse is less valuable than bounded memory, bandwidth, and latency.

Use `httptrace.ClientTrace` to verify behavior rather than inferring it:

```go
trace := &httptrace.ClientTrace{
	GotConn: func(info httptrace.GotConnInfo) {
		metrics.Connection(info.Reused, info.WasIdle)
	},
	PutIdleConn: func(err error) {
		metrics.IdleReturn(err)
	},
}
req = req.WithContext(httptrace.WithClientTrace(req.Context(), trace))
```

`PutIdleConn` is not called for HTTP/2. Trace hooks can run concurrently; any
recorder they share must be concurrency-safe and callbacks must stay cheap.

## Configure and share clients deliberately

Build from a clone of `http.DefaultTransport` so proxy behavior and maintained
defaults are retained, then change only policy supported by measurements and
capacity limits:

```go
func newHTTPClient() *http.Client {
	dialer := &net.Dialer{
		Timeout: 3 * time.Second,
		KeepAliveConfig: net.KeepAliveConfig{
			Enable:   true,
			Idle:     30 * time.Second,
			Interval: 10 * time.Second,
			Count:    3,
		},
	}

	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.DialContext = dialer.DialContext
	transport.MaxIdleConns = 256
	transport.MaxIdleConnsPerHost = 64
	transport.MaxConnsPerHost = 128
	transport.IdleConnTimeout = 60 * time.Second
	transport.TLSHandshakeTimeout = 5 * time.Second
	transport.ResponseHeaderTimeout = 5 * time.Second

	return &http.Client{Transport: transport}
}
```

These numbers are examples, not defaults to copy. Size them from expected
in-flight requests, HTTP version, upstream capacity, memory, and failure tests.

- `MaxIdleConnsPerHost` controls idle HTTP/1 capacity for an origin. Its
  default is two, which is often below service concurrency.
- `MaxConnsPerHost` bounds dialing, active, and idle connections per origin.
  Waiting for a slot is backpressure and is canceled with the request.
- `MaxIdleConns` is a global idle-pool limit across origins; too small a value
  causes idle connections for busy origin sets to evict each other.
- `IdleConnTimeout` controls how long the client retains an unused connection.
  Coordinate it with peer and proxy behavior, but measure before shortening it
  enough to cause handshake churn.
- `MaxResponseHeaderBytes` bounds response-header memory at a trust boundary.
  `ReadBufferSize` and `WriteBufferSize` are per connection; change their 4 KiB
  defaults only when syscall and memory measurements justify the multiplier.
- `ExpectContinueTimeout` only affects requests using `Expect: 100-continue`.
  Waiting allows an early rejection before a large upload; zero sends the body
  immediately. Choose based on the peer and upload cost.

Reuse configured clients and transports. Constructing a custom transport per
request fragments its connection pools; constructing a client per request is
usually unnecessary even when it uses a shared transport. Configure a
transport before first use and then treat it as immutable. Call
`CloseIdleConnections` when retiring a transport; it does not interrupt
requests already using a connection.

A single transport can safely serve many origins. Pools and
`MaxConnsPerHost` are keyed per origin, so a slow host does not consume another
host's per-host connection allowance. Origins still share `MaxIdleConns`, CPU,
memory, and any application-wide concurrency budget. Give an upstream its own
transport when it needs distinct TLS roots, proxying, connection limits,
timeouts, protocol policy, or isolation. Different `http.Client` values can
share a transport when only redirect, cookie, or whole-request policy differs.

## Timeouts, cancellation, and retries

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
Attempt limits, circuit breaking, hedging, and load shedding belong in the
[scaling and resilience guide](scaling-and-resilience.md).

## HTTP servers

Set resource limits from the endpoint contract:

```go
srv := &http.Server{
	Addr:              ":8080",
	Handler:           handler,
	ReadHeaderTimeout: 5 * time.Second,
	IdleTimeout:       90 * time.Second,
	MaxHeaderBytes:    1 << 20,
}
```

`ReadHeaderTimeout` bounds slow header delivery. `ReadTimeout` is an absolute
limit for reading the entire request, including the body; a single global value
may be unsuitable when legitimate upload sizes differ. Bound request bodies
with `http.MaxBytesReader`, then apply endpoint-specific context or read policy.

`WriteTimeout` is also an absolute connection deadline associated with the
request; it is not refreshed for every response write. It is useful for
bounded responses but can terminate a legitimate long stream. Streaming
servers commonly leave the global value unset and use
`http.NewResponseController(w).SetWriteDeadline` to establish appropriate
per-write deadlines. Check the returned error because a wrapped writer may not
support deadline control, and set a new deadline before the old one expires.

`http.TimeoutHandler` is suitable for bounded, bufferable handlers. It returns
503 after the deadline, cancels the handler context, and rejects later handler
writes, but code that ignores cancellation can keep running. It does not expose
`Flusher` or `Hijacker`, so it is not a streaming wrapper.

Additional high-value server rules:

- validate header, body, decompressed, and response sizes at trust boundaries;
- avoid materializing a full response when a streaming encoder can write it
  with bounded memory;
- when a response is small and known, one coherent write can reduce encoding
  and framing work, but do not pool buffers without allocation evidence;
- compress only compressible content above a measured threshold, and include
  decompression limits in the security contract;
- stop admitting requests before graceful drain and give shutdown a deadline.

`Server.Shutdown` and signal ownership are covered in
[Concurrency](concurrency.md#process-signals-and-graceful-shutdown). Hijacked
and upgraded connections need their own drain protocol.

## HTTP/2

HTTP/2 multiplexes streams on a connection, so HTTP/1 connection arithmetic no
longer predicts request concurrency. One connection may carry many requests;
its flow-control windows and loss events affect all of them.

Go 1.26 exposes protocol selection and HTTP/2 controls in `net/http`. The
following values are illustrative and require failure and memory tests:

```go
protocols := new(http.Protocols)
protocols.SetHTTP1(true)
protocols.SetHTTP2(true)

transport.Protocols = protocols
transport.HTTP2 = &http.HTTP2Config{
	StrictMaxConcurrentRequests: true,
	SendPingTimeout:             30 * time.Second,
	PingTimeout:                 10 * time.Second,
	WriteByteTimeout:            15 * time.Second,
	CountError: func(kind string) {
		metrics.HTTP2Error(kind)
	},
}

srv.Protocols = protocols
srv.HTTP2 = &http.HTTP2Config{
	MaxConcurrentStreams: 256,
	WriteByteTimeout:     15 * time.Second,
}
```

Do not share one mutable `Protocols` value if client and server policy may
diverge; the example uses one only because both sets are identical and fixed
before use.

`StrictMaxConcurrentRequests` makes a client wait when the peer's stream limit
is exhausted instead of opening additional connections. That is useful
backpressure when queueing is bounded by request contexts; it can reduce
throughput when one connection is unhealthy. `MaxConcurrentStreams` is a
server-advertised stream limit, not a global application work limit. Keep the
application's CPU and downstream semaphore as well.

The HTTP/2 receive-window and header-table fields trade memory for throughput.
Frame-size controls have similar protocol constraints, and all of these costs
multiply by connections or streams. Leave defaults until flow-control stalls
or memory are observed. Keep `PermitProhibitedCipherSuites` false. Use
`CountError`, connection metrics, and load tests before changing controls. The
callback can run concurrently and must remain concurrency-safe and cheap.
Unencrypted HTTP/2 is a separate explicit `Protocols` option; enable it only
for a protocol and trust environment that require it.

If custom dial or TLS hooks are added to a transport on an older-compatible
configuration path, verify HTTP/2 is still negotiated. On current Go,
`Protocols` is the clearest explicit policy; `ForceAttemptHTTP2` remains the
compatibility switch for transports configured with custom dialing or TLS.

## TLS

Connection reuse removes TLS handshakes entirely. Session resumption helps when
a fresh connection is unavoidable, but clients must opt into a session cache:

```go
tlsConfig := &tls.Config{
	// turbo: retains bounded client session state to reduce measured fresh-
	// connection handshake work; verify hits through DidResume.
	MinVersion:         tls.VersionTLS12,
	ClientSessionCache: tls.NewLRUClientSessionCache(128),
}

transport.TLSClientConfig = tlsConfig
transport.ForceAttemptHTTP2 = true
```

A nil client session cache disables client-side ticket use. Size the cache from
the number of distinct server session keys the client contacts, not request
count. The cache is safe for concurrent use.

Servers automatically manage and rotate ticket keys when explicit keys are not
configured. Replicas terminating the same hostname need an intentional key
sharing and rotation design if sessions should resume across replicas. Use
`SetSessionTicketKeys`, put the new encryption key first while retaining
limited old decryption keys, protect the keys like credentials, and exercise
rotation. Do not freeze the deprecated single `SessionTicketKey` in config.

Verify resumption instead of assuming it:

```go
trace := &httptrace.ClientTrace{
	TLSHandshakeDone: func(state tls.ConnectionState, err error) {
		metrics.TLSHandshake(state.DidResume, state.Version, err)
	},
}
```

For a controlled test, complete one response so the client can receive a
ticket, close idle TCP connections, and make a second connection while reusing
the same `ClientSessionCache`. `ConnectionState.DidResume` is the authority.
Normal connection reuse produces no handshake hook at all. Resumption reduces
handshake CPU and bytes; do not describe ordinary TLS-over-TCP resumption as
zero-latency early data.

Keep certificate verification enabled. Custom `VerifyPeerCertificate` is not
called on resumed sessions; use `VerifyConnection` when a custom check must run
for both full and resumed handshakes. Prefer Go's maintained cipher and curve
defaults. TLS 1.3 cipher suites are not configurable, legacy
`PreferServerCipherSuites` has no effect, and overriding curve preferences can
silently discard current security improvements. Change them only for a tested
compatibility or security requirement. Certificate chains and signature
algorithms also affect handshake bytes and CPU; choose them under the security
and client-compatibility contract, then benchmark the supported alternatives.

ALPN decides whether HTTPS uses HTTP/2. Let `net/http` configure it through its
protocol policy. Raw TLS protocols must set `NextProtos` consistently on both
sides and verify `ConnectionState.NegotiatedProtocol`.

## DNS

Name resolution is platform- and configuration-dependent. On Unix, Go may use
its built-in resolver or the native resolver through cgo. Diagnose the actual
choice in a staging or diagnostic run:

```sh
GODEBUG=netdns=1 ./service
GODEBUG=netdns=go+1 ./service
GODEBUG=netdns=cgo+1 ./service
```

The first prints the resolver decision; the latter two force a resolver and
print diagnostics. A forced choice can change compatibility with the host's
name-service configuration, so it is an experiment, not a blanket production
optimization. `net.Resolver.PreferGo` scopes the preference to one resolver.

Attach `httptrace` DNS and connect hooks to measure lookup count, duration,
addresses, and errors. A trace callback may occur more than once because of
address fallback. Reused transport connections perform no lookup, so DNS
metrics must be interpreted alongside reuse and dial metrics.

`net.Resolver` does not promise an application-level TTL cache. A native
resolver may benefit from operating-system caching, while the built-in path may
query configured resolvers. If lookups dominate after connection reuse is
healthy, prefer a well-operated local caching resolver. An in-process cache
must honor positive and negative TTLs, coalesce concurrent misses, rotate
addresses, bound memory, and define stale/failure behavior. Pinning one resolved
IP can defeat load balancing and failover.

Long-lived connections naturally outlive DNS answers. Decide whether endpoint
changes are adopted through server-driven drain, bounded connection lifetime,
idle eviction, or an address-aware dial policy. Dialing every request solely to
refresh DNS trades the problem for handshake and port cost.

## Socket and operating-system controls

Socket options are platform-specific paid optimizations. Put them in files with
appropriate build tags and propagate both the `RawConn.Control` error and the
option-setting error:

```go
func enableReusePort(_ string, _ string, raw syscall.RawConn) error {
	// turbo: enables measured multi-process accept scaling at the cost of
	// platform-specific listener semantics.
	var optionErr error
	controlErr := raw.Control(func(fd uintptr) {
		optionErr = unix.SetsockoptInt(
			int(fd),
			unix.SOL_SOCKET,
			unix.SO_REUSEPORT,
			1,
		)
	})
	if controlErr != nil {
		return controlErr
	}
	return optionErr
}

lc := net.ListenConfig{Control: enableReusePort}
listener, err := lc.Listen(ctx, "tcp", ":8080")
```

The file descriptor is valid only during the callback and must not be retained.
`ListenConfig.Control` runs after socket creation and before bind;
`Dialer.ControlContext` runs before connect. `SO_REUSEPORT` behavior differs by
operating system and is useful mainly for deliberate multi-listener or
multi-process designs. It is not required to distribute work within one normal
Go server.

Other controls:

- `TCP_NODELAY` is already enabled by default on `net.TCPConn`. Re-enable
  Nagle's algorithm only when a bulk-small-write benchmark supports the
  latency trade.
- `SetReadBuffer` and `SetWriteBuffer` request kernel buffer sizes. Check their
  errors. Tune from bandwidth-delay product, autotuning behavior, memory per
  connection, and queueing latency—not a copied constant.
- `net.KeepAliveConfig` exposes enablement, idle time, probe interval, and
  count where the OS supports them. Keepalive detects dead peers eventually;
  it is not a replacement for operation deadlines or application heartbeats.
- leave `SetLinger` at its default unless teardown semantics have been tested.
  A zero linger can discard unacknowledged data and turn close into a reset.
- file-descriptor limits and the listen backlog are deployment capacity. Check
  effective limits and saturation metrics before changing host policy. Go
  derives the TCP listen backlog from the operating system; an application
  cannot fix an undersized host limit with handler micro-optimizations.

## Long-lived and high-count connections

Go's runtime network poller parks goroutines waiting on supported network
descriptors instead of assigning an operating-system thread to every blocked
connection. A goroutine-per-connection design is therefore a strong baseline.
Blocking regular-file calls, cgo, and unsupported descriptors have different
scheduler behavior; confirm with profiles and trace.

On ordinary platforms the process begins with a 2 KiB minimum new-stack model;
stacks grow, can shrink, and the runtime may adapt later starting sizes from
observed use. Connection memory is still dominated easily by read/write
buffers, TLS state, queued messages, timers, and referenced application
objects. Measure retained bytes per idle and active connection, then multiply
by the target count.

Use absolute deadlines correctly:

```go
func exchange(conn net.Conn, request []byte, response []byte) error {
	if err := conn.SetWriteDeadline(time.Now().Add(5 * time.Second)); err != nil {
		return err
	}
	if _, err := conn.Write(request); err != nil {
		return err
	}

	if err := conn.SetReadDeadline(time.Now().Add(30 * time.Second)); err != nil {
		return err
	}
	_, err := io.ReadFull(conn, response)
	return err
}
```

Refresh an idle deadline after meaningful progress; setting it once creates a
total lifetime. A canceled context does not itself interrupt an arbitrary
`net.Conn.Read`. The connection owner should close the connection or set an
immediate deadline, then join the I/O goroutine. `Close` unblocks pending reads
and writes. Use `CloseWrite` or `CloseRead` only when the protocol defines a
half-close.

Bound write queues per connection in bytes and messages. A slow peer must not
retain an unlimited stream of application data or block unrelated peers. Make
the full-queue action explicit: block with a deadline, coalesce replaceable
updates, reject, or disconnect. Do not launch one unbounded goroutine per
message; hand CPU-heavy work to a bounded shared pool.

Pool per-connection buffers only after an allocation/GC profile justifies the
additional lifetime rules. A pooled buffer cannot be returned while any queued
slice or asynchronous writer still references it.

## Connection lifecycle observability

Every connection should be explainable from creation to teardown:

1. resolution and selected address for outbound connections;
2. dial or accept latency and error;
3. TLS version, ALPN, resumption, and handshake error where applicable;
4. protocol requests or frames, bounded queue delay, and byte counts;
5. terminal read/write/context error;
6. close result and total lifetime.

For raw connections, wrap byte counts without logging on every operation:

```go
type meteredConn struct {
	net.Conn
	read    atomic.Uint64
	written atomic.Uint64
}

func (c *meteredConn) Read(p []byte) (int, error) {
	n, err := c.Conn.Read(p)
	c.read.Add(uint64(n))
	return n, err
}

func (c *meteredConn) Write(p []byte) (int, error) {
	n, err := c.Conn.Write(p)
	c.written.Add(uint64(n))
	return n, err
}

func serveConnection(raw net.Conn) {
	c := &meteredConn{Conn: raw}
	started := time.Now()
	var terminalErr error
	defer func() {
		closeErr := c.Close()
		metrics.ConnectionClosed(
			time.Since(started),
			c.read.Load(),
			c.written.Load(),
			terminalErr,
			closeErr,
		)
	}()
	terminalErr = runProtocol(c) // joins any child I/O goroutines
}
```

Give exactly one owner responsibility for close and final emission. If reads
and writes run in child goroutines, cancel them, close to unblock them, wait for
both, and only then publish the final summary. Record error classes rather than
payloads or secrets; sample detailed events and keep aggregate counters and
histograms cheap.

On HTTP clients, `httptrace` exposes DNS, connect, TLS, connection reuse,
request-write, and first-response-byte phases. On servers, `ConnContext` can
attach a connection identity and `ConnState` can maintain lifecycle counts.
`ConnState` callbacks are concurrent and must not block. A hijacked connection
leaves HTTP ownership at `StateHijacked` and will not later report
`StateClosed`; the upgraded protocol must emit its own close event.

Correlate connection identity with request or stream identity. A single HTTP/2
connection carries many concurrent streams, so a connection-level latency
histogram cannot replace request-level observations.

## Profile under network-shaped load

Use a workload that includes realistic payloads, connection reuse, connection
churn, slow peers, cancellation, downstream saturation, and TLS. Loopback-only
benchmarks omit the latency and loss behavior that often determines the design.

Collect together:

- throughput, error rate, and latency percentiles;
- active, idle, dialing, queued, rejected, and closed connection counts;
- bytes and allocations per request or frame;
- CPU, heap, goroutine, block, and mutex profiles;
- scheduler and network-blocking evidence from `go tool trace`;
- OS descriptors, backlog drops, retransmits, resets, and socket memory.

Profile logging and metrics overhead too. Per-packet or per-read logs can change
the system being measured. Prefer aggregate lifecycle events, sampling, and
bounded-cardinality labels.

Run `go test -race` after changes to connection ownership, callbacks, buffers,
or transport state. Then compare repeated benchmarks or load-test trials. Stop
when application and protocol bounds meet the objective; event loops, raw
syscalls, custom DNS caches, buffer pools, and manual socket policy require
their own before/after evidence and an explicit maintenance tradeoff.

## Version compatibility

The `http.Protocols`, `http.HTTP2Config`, and `net.KeepAliveConfig` examples
describe Go 1.26 APIs. Older supported toolchains need their documented
`net/http` policy and, when explicit HTTP/2 controls are genuinely required, a
compatible `golang.org/x/net/http2` configuration. Do not add that dependency
or raise the module's Go version solely to copy a tuning example. Verify
protocol negotiation and behavior on the repository's minimum toolchain and
keep default settings when an older API cannot express a measured knob safely.
