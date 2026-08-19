# HTTP/2 Tuning

Stream limits, flow-control windows, and the failure modes that only appear when
one connection carries everything.

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
