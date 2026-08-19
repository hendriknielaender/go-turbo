# TLS

Handshakes are paid on the connections a pool fails to reuse, not on steady
traffic. Fix reuse first, then look at resumption and cipher selection.

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
