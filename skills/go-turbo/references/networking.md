# Networking

`net/http` defaults are tuned for correctness and convenience, not for a
service under sustained load. Most production networking problems in Go trace
back to three things: connections that aren't being reused, timeouts that
aren't set, and unbounded concurrency against a downstream that can't take
it.

## Contents

- [Connection reuse (the big one)](#connection-reuse-the-big-one)
- [Tuning http.Transport](#tuning-httptransport)
- [One client per upstream](#one-client-per-upstream)
- [Server-side settings](#server-side-settings)
- [TLS](#tls)
- [DNS](#dns)
- [Socket options](#socket-options)
- [Long-lived connections](#long-lived-connections)
- [Observability](#observability)

## Connection reuse (the big one)

Before tuning anything, check that connections are actually being reused. A
client that opens a fresh TCP connection (and TLS handshake) per request is
paying 1–2 round trips of pure latency every time, burning ephemeral ports,
and accumulating sockets in `TIME_WAIT`.

The most common cause is not draining the response body. The transport can
only return a connection to the pool once the body is fully read **and**
closed:

```go
resp, err := client.Do(req)
if err != nil {
    return err
}
defer resp.Body.Close()

// Even when you don't want the body — especially then.
io.Copy(io.Discard, resp.Body)
```

Close alone is not enough. Closing an unread body forces the transport to
discard the connection. If bodies could be large and you genuinely don't want
them, cap the drain (`io.CopyN(io.Discard, resp.Body, 64<<10)`) rather than
reading unboundedly.

Verify with `httptrace` before assuming:

```go
trace := &httptrace.ClientTrace{
    GotConn: func(i httptrace.GotConnInfo) {
        log.Printf("reused=%v idle=%v", i.Reused, i.WasIdle)
    },
}
req = req.WithContext(httptrace.WithClientTrace(req.Context(), trace))
```

`reused=false` on every request means the pool isn't working, and no amount
of transport tuning will fix the underlying cause.

## Tuning http.Transport

```go
transport := &http.Transport{
    MaxIdleConns:          1000,              // total across all hosts
    MaxIdleConnsPerHost:   100,               // default is 2 — usually the bug
    MaxConnsPerHost:       200,               // hard cap, includes in-use
    IdleConnTimeout:       90 * time.Second,
    ExpectContinueTimeout: 0,
    TLSHandshakeTimeout:   5 * time.Second,
    ResponseHeaderTimeout: 5 * time.Second,
    ForceAttemptHTTP2:     true,
    DialContext: (&net.Dialer{
        Timeout:   3 * time.Second,
        KeepAlive: 30 * time.Second,
    }).DialContext,
}

client := &http.Client{
    Transport: transport,
    Timeout:   10 * time.Second,
}
```

The fields that matter most, and why:

- **`MaxIdleConnsPerHost`** defaults to 2. For a service making concurrent
  calls to one upstream, that means almost every request beyond the second
  opens a new connection. This single field is the most common `net/http`
  performance fix. Set it at or above your expected concurrency to that host.
- **`MaxConnsPerHost`** is the ceiling on total connections (idle + active)
  per host. Unset, it's unlimited, which turns a downstream slowdown into a
  connection stampede that makes the slowdown worse. Set it to something the
  downstream can actually serve.
- **`IdleConnTimeout`** should sit *below* any intermediate proxy or load
  balancer idle timeout. If the LB closes at 60s and you idle at 90s, you
  periodically send requests onto connections the peer has already closed and
  get sporadic, hard-to-reproduce EOFs.
- **`ExpectContinueTimeout: 0`** skips the 100-continue wait for large
  request bodies when the server doesn't implement it — a full second of
  dead time per request otherwise.
- **`ResponseHeaderTimeout`** bounds time-to-first-byte specifically, which
  catches a hung upstream faster than the overall client timeout.

`http.Client.Timeout` covers the whole request including body read. Keep it
tight and use retries with backoff and jitter instead of a long timeout — a
30-second timeout holds a goroutine, its buffers, and a socket for 30 seconds
under a failure that will not recover.

Per-request deadlines should come from `context`, so cancellation propagates.
`Client.Timeout` is the backstop.

## One client per upstream

Sharing one `http.Client` across unrelated upstreams shares the connection
pool. `MaxIdleConns` and `MaxConnsPerHost` then apply across services that
have nothing to do with each other: a slow dependency can starve the pool for
a fast one, and head-of-line effects become impossible to attribute.

Construct one client per upstream, each with limits sized to that
dependency's capacity and latency profile. Do reuse each client — creating an
`http.Client` per request creates a transport per request, which defeats
pooling entirely and leaks connections until GC.

## Server-side settings

```go
srv := &http.Server{
    Addr:              ":8080",
    Handler:           mux,
    ReadHeaderTimeout: 5 * time.Second,   // slowloris defense
    ReadTimeout:       15 * time.Second,
    WriteTimeout:      15 * time.Second,
    IdleTimeout:       120 * time.Second,
    MaxHeaderBytes:    1 << 20,
}
```

A server with no timeouts holds a goroutine and its buffers for every stalled
client indefinitely. `ReadHeaderTimeout` in particular is the defense against
a client that opens a connection and dribbles headers forever.

Other things that matter more than micro-tuning handlers:

- **Set `Content-Length` when you know it**, or write the whole response at
  once. Otherwise the server uses chunked encoding, which adds framing
  overhead per write.
- **`http.ResponseWriter` is buffered but not infinitely.** Many small
  `Write` calls each cross into the transport; build the response in a
  (pooled) buffer and write once.
- **Compress selectively.** gzip on a 200-byte JSON response costs more CPU
  than it saves bytes. Threshold around 1 KB, and skip already-compressed
  content types.
- **`http.TimeoutHandler`** bounds handler execution, but note it doesn't
  stop the handler goroutine — it just stops waiting for it. Cancellation
  still has to come from `ctx`.

For extreme connection counts where the goroutine-per-connection model itself
is the cost, event-loop libraries (`cloudwego/netpoll`, `tidwall/evio`) trade
standard-library compatibility for lower per-connection overhead. That's a
last resort after transport tuning, buffer pooling, and payload reduction —
and it means giving up `net/http`, middleware ecosystems, and HTTP/2 support.

## TLS

TLS cost is concentrated in the handshake: two round trips and asymmetric
crypto (TLS 1.3 cuts it to one, and zero on resumption). Steady-state
symmetric encryption with AES-GCM on hardware with AES-NI is nearly free.

So the optimization is almost entirely "handshake less":

1. **Reuse connections.** A reused connection has no handshake at all. This
   dominates every other TLS tuning decision.
2. **Enable session resumption.** On by default in Go's server via rotating
   session ticket keys. If you terminate TLS across multiple instances behind
   a load balancer, they need a shared `SessionTicketKey` or clients will
   fail to resume when they land on a different instance. Rotate it
   periodically.
3. **Prefer TLS 1.3.** `MinVersion: tls.VersionTLS13` where clients allow it:
   one round trip for a full handshake, zero for resumption.
4. **Set `NextProtos`.** Without ALPN, clients assume HTTP/1.1 and you lose
   HTTP/2 silently. Order matters — the server picks the first mutually
   supported entry.

```go
cfg := &tls.Config{
    MinVersion: tls.VersionTLS12,
    NextProtos: []string{"h2", "http/1.1"},
}
```

On cipher suites: Go's defaults are good and, for TLS 1.3, `CipherSuites` is
ignored entirely — the suite set is fixed. For TLS 1.2, if you must
configure, prefer ECDHE key exchange (forward secrecy, cheaper than RSA) with
AES-GCM where AES-NI is available and ChaCha20-Poly1305 where it isn't; Go
already picks between those based on hardware support. `PreferServerCipherSuites`
has been a no-op since Go 1.17. Overriding defaults here usually makes things
less secure without making them faster.

ECDSA certificates verify faster and produce smaller signatures than RSA;
that's a real saving on a handshake-heavy path.

Certificate verification caching is possible via `VerifyPeerCertificate`, but
it is easy to get wrong in ways that silently accept bad certificates.
Handshake avoidance is safer and buys more.

## DNS

Go has no built-in DNS cache. The resolver is either the pure-Go one
(default) or cgo's `getaddrinfo` (when the build uses cgo and the system
config requires it — `GODEBUG=netdns=go|cgo` forces the choice, and
`netdns=1` prints which is in use).

The subtlety that bites people: because `http.Transport` pools connections,
DNS is *not* re-resolved for a reused connection. In an environment where
backend IPs change under a stable name — Kubernetes services, blue/green
deploys, failover — a long-lived pooled connection keeps talking to the old
address indefinitely. `IdleConnTimeout` bounds how long that can persist,
which is another reason not to set it too high.

If you need faster propagation, dial fresh per request (costs a handshake) or
resolve explicitly and manage the address list yourself. For the opposite
problem — resolution showing up in latency profiles — put a caching resolver
in front (`dnsmasq`, `systemd-resolved`, or NodeLocal DNSCache in Kubernetes)
rather than building one in the process. Measure with `httptrace`'s
`DNSStart`/`DNSDone` hooks before assuming DNS is the problem.

## Socket options

These are last-resort tuning, reached for after the application-level items
above. All of them are set through `net.ListenConfig`/`net.Dialer`'s
`Control` callback, which runs before `bind`/`connect` — set them anywhere
else and the kernel ignores them.

**`TCP_NODELAY`** disables Nagle's algorithm, which otherwise delays small
writes waiting to coalesce them. Go **already disables Nagle by default** on
TCP connections, which surprises people arriving from C. `SetNoDelay(false)`
re-enables it, which is occasionally right for bulk transfer of many small
writes where bandwidth beats latency.

**`SO_REUSEPORT`** lets multiple sockets bind the same port, with the kernel
distributing incoming connections across their accept queues. Useful for
multi-process deployments and for zero-downtime restarts. Rarely needed for
a single Go process — the runtime already distributes accepted connections
across all Ps.

```go
lc := net.ListenConfig{
    Control: func(network, address string, c syscall.RawConn) error {
        return c.Control(func(fd uintptr) {
            unix.SetsockoptInt(int(fd), unix.SOL_SOCKET, unix.SO_REUSEPORT, 1)
        })
    },
}
ln, err := lc.Listen(ctx, "tcp", ":8080")
```

**`SO_RCVBUF` / `SO_SNDBUF`** size the kernel's per-socket buffers.

```go
tc := conn.(*net.TCPConn)
tc.SetReadBuffer(256 << 10)
tc.SetWriteBuffer(256 << 10)
```

Too small and the kernel wakes you constantly and can't keep the link busy;
too large and you waste memory and add queueing latency. The target is the
bandwidth-delay product (`bandwidth × RTT`) — that's how much data must be in
flight to keep a high-latency link saturated. Linux autotunes within a range
by default and usually does fine; override for long-fat networks (high
bandwidth, high RTT) after measuring, and remember it multiplies by
connection count.

**Keepalives** detect dead peers. Go enables them with a default period.
`SetKeepAlivePeriod` sets only the idle time before the first probe
(`TCP_KEEPIDLE`); the probe interval and count (`TCP_KEEPINTVL`,
`TCP_KEEPCNT`) need raw socket options, and without tuning those a dead peer
can take minutes to detect. Go 1.23+ exposes all three via
`net.KeepAliveConfig`:

```go
d := net.Dialer{
    KeepAliveConfig: net.KeepAliveConfig{
        Enable:   true,
        Idle:     30 * time.Second,
        Interval: 10 * time.Second,
        Count:    3,
    },
}
```

Values in the 30–60s idle / 10–15s interval / 3–5 probes range are common
operational practice, chosen to fire before typical cloud load balancer
idle timeouts. They aren't specified by any standard. Aggressive settings
risk false positives on congested links.

**`somaxconn`** bounds the pending-connection queue. When it fills, the
kernel drops SYNs and clients see refused connections or long retries — which
looks like a service outage during a burst even though the process is
healthy. It's a system-level setting (`sysctl -w net.core.somaxconn=4096`),
and note Go's `Listen` passes a backlog derived from it.

## Long-lived connections

WebSockets, streaming RPCs, and persistent TCP sessions fail differently from
request/response: problems accumulate over hours instead of appearing under
load.

**Always set deadlines.** A read with no deadline on a connection whose peer
vanished blocks forever, holding a goroutine and its buffers. Multiply by the
connection count.

```go
const idle = 60 * time.Second

for {
    conn.SetReadDeadline(time.Now().Add(idle))
    n, err := conn.Read(buf)
    if err != nil {
        return   // includes timeout — treat as a dead peer
    }
    conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
    if _, err := conn.Write(resp); err != nil {
        return
    }
}
```

Refresh the deadline on every operation rather than setting it once — a
deadline is an absolute time, not a per-call timeout.

**Copy before handing off.** The retained-backing-array trap
(`references/allocation.md`) is at its worst here: a sub-slice of a
per-connection read buffer, sent to a queue, keeps the whole buffer alive for
as long as it's queued.

**Bound per-connection state.** Every buffer, queue, and pending-write slice
is multiplied by connection count. 64 KB of per-connection buffers is 640 MB
at 10,000 connections.

**Give every reader goroutine an exit.** A `select` on `ctx.Done()` alongside
the read, and a connection close from the cancellation path so a blocked read
actually returns.

## Observability

Instrument before tuning. `httptrace` gives per-request phase timings on the
client side:

```go
var dnsStart, connStart, tlsStart time.Time
trace := &httptrace.ClientTrace{
    DNSStart:     func(httptrace.DNSStartInfo) { dnsStart = time.Now() },
    DNSDone:      func(httptrace.DNSDoneInfo) { metrics.DNS(time.Since(dnsStart)) },
    ConnectStart: func(_, _ string) { connStart = time.Now() },
    ConnectDone:  func(_, _ string, _ error) { metrics.Dial(time.Since(connStart)) },
    TLSHandshakeStart: func() { tlsStart = time.Now() },
    TLSHandshakeDone:  func(tls.ConnectionState, error) { metrics.TLS(time.Since(tlsStart)) },
    GotConn:      func(i httptrace.GotConnInfo) { metrics.Reused(i.Reused) },
}
```

Server side, `ConnState` tracks the connection lifecycle
(`StateNew`/`StateActive`/`StateIdle`/`StateClosed`), which is how you find
connections that never close and idle counts that never drain.

Log volume is itself a performance problem at scale: per-connection logging
at 10k connections generates enough I/O and allocation to change the numbers
you're trying to measure. Prefer counters and histograms; sample logs; log
once per connection at close with an aggregate rather than per event.
