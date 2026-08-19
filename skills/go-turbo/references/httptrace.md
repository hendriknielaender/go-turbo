# Connection Observability

`httptrace` tells you whether a connection was reused, how long the handshake
took, and where the time before the first byte went.

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
