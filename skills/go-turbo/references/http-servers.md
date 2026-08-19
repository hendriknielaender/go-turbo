# HTTP Servers

A server's job under load is to bound what it accepts and release resources on
every path, including the ones that fail. Timeouts come first.

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
[Graceful Shutdown](graceful-shutdown.md). Hijacked
and upgraded connections need their own drain protocol.

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
