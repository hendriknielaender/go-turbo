# Socket Options

The last layer, below protocol and application boundaries. Reach here once those
are measured and the remaining cost is kernel buffers or the option set.

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
