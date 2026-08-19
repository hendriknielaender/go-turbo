# HTTP Client Configuration

A client and its transport have different sharing rules. Configure the transport
once and share it; per-request construction fragments the pool.

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

## Version compatibility

The `http.Protocols`, `http.HTTP2Config`, and `net.KeepAliveConfig` examples
describe Go 1.26 APIs. Older supported toolchains need their documented
`net/http` policy and, when explicit HTTP/2 controls are genuinely required, a
compatible `golang.org/x/net/http2` configuration. Do not add that dependency
or raise the module's Go version solely to copy a tuning example. Verify
protocol negotiation and behavior on the repository's minimum toolchain and
keep default settings when an older API cannot express a measured knob safely.
