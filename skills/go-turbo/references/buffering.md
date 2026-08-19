# I/O Buffering

Repeated small reads and writes are the cost; buffering is the fix, provided the
flush and error contract stays explicit.

## Buffer repeated I/O

Small writes made directly to a file or socket may each reach the operating
system. A `bufio.Writer` combines them. Flush before closing and report both
flush and close errors:

```go
func writeLines(path string, lines []string) (retErr error) {
	f, err := os.Create(path)
	if err != nil {
		return err
	}

	w := bufio.NewWriter(f)
	defer func() {
		retErr = errors.Join(retErr, w.Flush())
		retErr = errors.Join(retErr, f.Close())
	}()

	for _, line := range lines {
		if _, err := w.WriteString(line); err != nil {
			return err
		}
		if err := w.WriteByte('\n'); err != nil {
			return err
		}
	}
	return nil
}
```

Closing the underlying file does not flush `bufio.Writer`. Conversely,
`Flush` only hands bytes to the underlying writer; it does not promise durable
storage. If the contract requires crash durability, define when `File.Sync`,
atomic rename, and directory synchronization are required and test failure
paths.

For reads, choose by token semantics:

- `bufio.Scanner` is convenient for bounded tokens. Its default maximum token
  size is `bufio.MaxScanTokenSize`; call `Buffer` before scanning when the
  protocol permits a larger, explicitly bounded token. Always check `Err`.
- `bufio.Reader` exposes delimiter and look-ahead operations without imposing
  Scanner's token model.
- direct `Read` is appropriate when the caller already supplies suitably sized
  buffers or the operation is genuinely one-shot.

Do not add buffering between interactive peers without deciding when to flush.
If each peer waits for buffered data from the other, the optimization becomes a
protocol deadlock.

## Size buffers from the workload

The default `bufio` size is 4 KiB. That is a library default, not a universal
page-size or storage-block guarantee. Increase it only when fewer calls improve
measured throughput for sustained transfers.

Account for multiplication:

```text
memory ~= live connections * (read buffer + write buffer + queued payloads)
```

A 64 KiB buffer can be insignificant for one bulk copy and expensive when kept
twice on every connection. Large buffers can also retain rare peak payloads.
Use a small matrix of sizes and report bytes/op, allocations/op, calls/op,
throughput, and tail latency. Keep the smallest size on the performance
plateau.

Preallocate only when a useful bound is known. An oversized buffer paid on
every request can cost more GC and resident memory than the calls it saves.
