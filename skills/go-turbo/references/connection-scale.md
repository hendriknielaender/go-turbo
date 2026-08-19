# High Connection Counts

Per-connection memory is the binding constraint long before CPU is. Budget it
explicitly, and tune the accept path once the count is genuinely high.

## Contents

- [Long-lived and high-count connections](#long-lived-and-high-count-connections)
- [Ten-thousand-plus connections](#ten-thousand-plus-connections)
- [Accept loops and operating-system tuning](#accept-loops-and-operating-system-tuning)

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

## Ten-thousand-plus connections

Large connection counts are a budget exercise, not a special Go mode. Account
for at least:

- **File descriptors:** listeners, accepted and outbound sockets, files,
  pipes, logs, and monitoring endpoints. Reserve headroom for reconnects and
  deployments rather than setting the process limit equal to target clients.
- **Memory:** goroutine stacks, connection structs, TLS and codec state,
  application read/write buffers, queued messages, and kernel socket buffers.
  Multiply measured per-connection live memory by the target plus headroom.
- **Ports and state tables:** outbound connections consume source-port and NAT
  state. Limits depend on the full address tuple, reuse, destination mix, and
  network devices; inbound accepted sockets do not consume local ephemeral
  ports in the same way.
- **Scheduler and CPU:** mostly idle sockets are different from thousands of
  simultaneously runnable handlers. Benchmark burst wakeups and broadcast
  patterns, not just an idle steady state.
- **Backlog and accept rate:** handshake queues and accepted-but-unhandled
  connections are finite. A larger backlog cannot repair a handler that never
  catches up.

Avoid per-connection timers, ticker goroutines, and fixed large buffers unless
measurements justify them. Deadlines integrated with the runtime are usually
cheaper and clearer. Bound outbound queues per connection so one slow client
cannot retain arbitrary messages. Sample high-cardinality connection details
rather than labeling metrics by peer.

## Accept loops and operating-system tuning

A raw accept loop must not spin on repeated errors. On shutdown, return. On a
resource-exhaustion or transient failure, log with rate limiting and retry with
a bounded exponential delay that resets after a successful accept. Continuing
immediately can consume a CPU while the descriptor shortage prevents recovery.

Operating-system limits, backlog semantics, socket-buffer accounting, and
network-stack controls vary by kernel, container runtime, and cloud platform.
Never paste system-control values as universal tuning. Record the observed
default and effective value on the deployment host, change one constraint at a
time, load-test it, and document rollback. Some settings belong to the host or
orchestrator and cannot be changed meaningfully inside a container.

Raising descriptor or backlog limits without bounding application memory and
work merely moves the crash. Verify graceful close, half-open peers, keepalive
policy, load-balancer idle timeouts, and restart waves at the target scale.
