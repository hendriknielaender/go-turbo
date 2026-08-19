# HTTP Connection Reuse

Nearly every slow HTTP client is a pool that is not being reused. Establish reuse
before tuning anything below it.

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
only a loopback throughput number. The decision matrix is in
`protocol-selection.md`.

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
