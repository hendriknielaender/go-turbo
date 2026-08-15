# I/O and syscalls

The dominant cost in an I/O path is usually the boundary crossed per item:
kernel calls, storage operations, database round trips, or protocol frames.
Reduce the number of crossings while preserving latency, durability, and error
semantics. Confirm the result with syscall counts, profiles, and realistic
throughput tests.

## Contents

- [Buffer repeated I/O](#buffer-repeated-io)
- [Size buffers from the workload](#size-buffers-from-the-workload)
- [Batch without holding locks across I/O](#batch-without-holding-locks-across-io)
- [Copy streams through existing fast paths](#copy-streams-through-existing-fast-paths)
- [Frame streams defensively](#frame-streams-defensively)
- [Choose a file-reading API](#choose-a-file-reading-api)
- [Memory mapping](#memory-mapping)
- [Version compatibility](#version-compatibility)

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

## Batch without holding locks across I/O

Batching amortizes fixed cost, but it creates queueing latency and a crash-loss
window. The batch contract must state its flush trigger, hard item and byte
bounds, maximum wait, ordering, and delivery semantics.

Never call a database, RPC, or user callback while holding the mutex that
protects the producer buffer. Detach the current slice under the lock, install
a different backing array, and flush the detached batch outside that lock.
Serialize flushes if ordering matters.

```go
type Batcher[T any] struct {
	mu      sync.Mutex
	flushMu sync.Mutex
	buf     []T
	spare   []T
	flushAt int
	write   func(context.Context, []T) error
}

func NewBatcher[T any](
	flushAt int,
	write func(context.Context, []T) error,
) (*Batcher[T], error) {
	if flushAt < 1 {
		return nil, fmt.Errorf("flush trigger must be positive: %d", flushAt)
	}
	if write == nil {
		return nil, errors.New("batch writer is nil")
	}
	return &Batcher[T]{
		buf:     make([]T, 0, flushAt),
		spare:   make([]T, 0, flushAt),
		flushAt: flushAt,
		write:   write,
	}, nil
}

func (b *Batcher[T]) Add(ctx context.Context, item T) error {
	if err := ctx.Err(); err != nil {
		return err
	}

	b.mu.Lock()
	b.buf = append(b.buf, item)
	full := len(b.buf) >= b.flushAt
	b.mu.Unlock()
	if !full {
		return nil
	}
	return b.Flush(ctx)
}

func (b *Batcher[T]) Flush(ctx context.Context) error {
	// Serialize detach plus delivery so batches cannot overtake one another.
	b.flushMu.Lock()
	defer b.flushMu.Unlock()

	b.mu.Lock()
	if len(b.buf) == 0 {
		b.mu.Unlock()
		return nil
	}
	batch := b.buf
	b.buf = b.spare[:0]
	b.spare = nil
	b.mu.Unlock()

	// write must not retain batch after returning; clone there if it must.
	err := b.write(ctx, batch)

	clear(batch) // release pointers before retaining the backing array
	b.mu.Lock()
	if cap(batch) == b.flushAt {
		b.spare = batch[:0]
	} else {
		// Do not retain a backing array grown by an unusual concurrent burst.
		b.spare = make([]T, 0, b.flushAt)
	}
	b.mu.Unlock()
	return err
}

func (b *Batcher[T]) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		return fmt.Errorf("flush interval must be positive: %s", interval)
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return context.Cause(ctx)
		case <-ticker.C:
			if err := b.Flush(ctx); err != nil {
				return err
			}
		}
	}
}
```

This design is safe for concurrent `Add` and `Flush`, does not expose a slice
that producers continue to mutate, serializes callbacks, propagates callback
errors, and stops its ticker. Producers may append while a slow flush runs, so
the trigger is not a hard queue bound. Bound their concurrency and add a byte
limit or a bounded input channel when item sizes or producer counts vary.

Run the timer loop under supervision and treat its returned error as fatal to
the batching pipeline. `Add` likewise returns a size-triggered flush error to
its caller. On shutdown, cancel and join producers, stop `Run`, then call
`Flush` with a new bounded shutdown context. The canceled run context is not a
usable flush context.

The writer owns the detached batch for the duration of its call. On error, the
batcher does not blindly requeue it because the writer may have committed a
prefix. The writer must provide transactional or idempotent semantics when
retries are required. Persist before acknowledging if process-crash loss is
unacceptable. The writer must not call `Add` or `Flush` on the same batcher;
flushes are serialized and such re-entry can deadlock. Run exactly one timer
loop per batcher.

For databases, use the driver's real bulk facility or a transaction with
prepared statements; concatenating SQL is neither a safe nor necessarily fast
batch. For sockets that support scatter/gather, `net.Buffers.WriteTo` may map
several byte slices to an OS-specific vector write without first concatenating
them. `WriteTo` consumes the `net.Buffers` slice headers, so reconstruct that
slice before reuse; it does not mutate the payload bytes.

## Copy streams through existing fast paths

`io.Copy` first uses `src.(io.WriterTo)`, then `dst.(io.ReaderFrom)`, and only
uses an internal scratch buffer when neither fast path exists. Preserve those
interfaces when wrapping files or connections; an unnecessary wrapper can hide
an optimized transfer path.

`io.CopyBuffer` lets the caller supply scratch space for the generic path:

```go
buf := make([]byte, 32<<10)
_, err := io.CopyBuffer(dst, src, buf)
```

The exact best size is workload-dependent. A buffer passed to `CopyBuffer` is
ignored when a `WriterTo` or `ReaderFrom` fast path applies. Never pass a
zero-length slice.

Pooling scratch space is a paid optimization. Use it only after the generic
copy allocation is visible and concurrent retained memory is acceptable:

```go
var copyBuffers = sync.Pool{
	New: func() any { return new([32 << 10]byte) },
}

func copyStream(dst io.Writer, src io.Reader) error {
	// turbo: pools 32 KiB scratch after copy allocation appeared in profiles;
	// callers and the copy operation must not retain the buffer.
	buf := copyBuffers.Get().(*[32 << 10]byte)
	defer copyBuffers.Put(buf)
	_, err := io.CopyBuffer(dst, src, buf[:])
	return err
}
```

`sync.Pool` may discard entries at any garbage collection and is not a capacity
reservation. Cap pooled object size, clear pointer-bearing data, and compare
`allocs/op` plus peak memory before keeping it.

Avoid converting between `[]byte` and `string` only to satisfy an intermediate
API. Prefer reader/writer or byte-oriented APIs through the pipeline. If a
consumer retains data read into reusable storage, copy the retained portion
into a right-sized slice at that ownership boundary.

## Frame streams defensively

TCP is a byte stream: a `Read` can return part of a frame or several frames.
Use a bounded framing format and `io.ReadFull` for fixed-width pieces.

```go
func readFrame(r *bufio.Reader, maxFrame int) ([]byte, error) {
	if maxFrame < 0 {
		return nil, fmt.Errorf("negative frame limit: %d", maxFrame)
	}
	header, err := r.Peek(4)
	if err != nil {
		return nil, err
	}
	encodedSize := binary.BigEndian.Uint32(header)
	if uint64(encodedSize) > uint64(maxFrame) {
		return nil, fmt.Errorf(
			"frame size %d exceeds limit %d",
			encodedSize,
			maxFrame,
		)
	}
	if _, err := r.Discard(4); err != nil {
		return nil, err
	}

	payload := make([]byte, int(encodedSize))
	if _, err := io.ReadFull(r, payload); err != nil {
		return nil, err
	}
	return payload, nil
}
```

Set a read deadline at the connection layer so a peer cannot reserve the
declared frame forever. Validate the length before conversion or allocation.
When reusing a payload buffer, document that the handler may not retain it; copy
only the portion that crosses into a longer lifetime.

`Peek` and methods such as `ReadSlice` return views into the reader's buffer.
Those bytes are invalidated by later reads. This is useful for synchronous
parsing and unsafe for asynchronous handoff without a copy.

## Choose a file-reading API

- `os.ReadFile` is clear for a file whose maximum size is trusted and small
  enough to hold in memory. Validate size at a trust boundary rather than
  assuming a configuration file is small.
- `bufio.Scanner` streams bounded tokens.
- `bufio.Reader` or a decoder over `io.Reader` streams structured data.
- `File.ReadAt` supports independent positional reads and is safe for
  concurrent calls. Avoid shared `Seek` plus `Read` across goroutines.
- `io.SectionReader` gives a bounded view over a `ReaderAt` without changing a
  shared file offset.

Whole-file reads and `io.ReadAll` intentionally allocate for the entire input.
Put an explicit byte limit before them for network input or untrusted files.
For sequential large files, buffered streaming is usually the simplest strong
baseline.

## Memory mapping

Mapping replaces explicit read syscalls with page faults and memory accesses.
It is only zero-copy when the algorithm works directly on the mapped bytes. If
those bytes are copied into another buffer, mapping avoided read calls but did
not avoid the copy.

```go
func withMappedFile(path string, use func([]byte) error) (retErr error) {
	// turbo: mmap removes measured read calls for stable large files at the
	// cost of platform-specific fault and lifetime semantics.
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer func() { retErr = errors.Join(retErr, f.Close()) }()

	info, err := f.Stat()
	if err != nil {
		return err
	}
	if info.Size() == 0 {
		return use(nil)
	}
	if info.Size() > int64(maxInt) {
		return fmt.Errorf("file is too large to map: %d", info.Size())
	}

	data, err := unix.Mmap(
		int(f.Fd()),
		0,
		int(info.Size()),
		unix.PROT_READ,
		unix.MAP_PRIVATE,
	)
	if err != nil {
		return err
	}
	defer func() { retErr = errors.Join(retErr, unix.Munmap(data)) }()
	return use(data)
}
```

`maxInt` is a local architecture-sized bound, for example `int(^uint(0) >> 1)`.
Place mapping code in platform-specific files. The callback must not retain the
slice after unmap.

Mapping has failure modes ordinary reads avoid: access can block on a page
fault, and truncating or mutating the mapped file can fault the process or
produce inconsistent observations. Atomic replacement normally leaves an
existing mapping attached to the old file object. Mapping lifetime is outside
normal Go heap accounting. Coordinate writers, bound mapping count and size,
and unmap deterministically. Random access and in-place scans of large, stable
files are plausible use cases; sequential reads need a benchmark before
accepting the added lifecycle and portability cost.

The final check is end-to-end. Fewer syscalls can still lose if batching raises
latency, buffers inflate memory, or a hidden copy remains. Keep the simplest
implementation that meets the measured service objective.

## Version compatibility

The generic batcher requires Go 1.18; `errors.Join` and `context.Cause` require
Go 1.20; and the `clear` built-in requires Go 1.21. On older supported modules,
use a typed batcher, return `ctx.Err()`, preserve multiple cleanup errors
explicitly, and zero pointer-bearing elements with a loop before retaining the
backing array. The mmap example uses
`golang.org/x/sys/unix`; select a dependency version compatible with the
module, keep it platform-tagged, and do not add it merely to avoid ordinary
file reads.
