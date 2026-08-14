# I/O and Syscalls

A syscall crosses from user space to kernel space: mode switch, possible
context switch, cache disruption. One is cheap. Ten thousand per second is a
bottleneck, and it will show up in a CPU profile as time in `syscall` with no
obvious hot function of your own.

Nearly all I/O optimization in Go is one idea applied at different scales:
**do the expensive crossing once per batch instead of once per item.**

## Contents

- [Buffering](#buffering)
- [Buffer sizing](#buffer-sizing)
- [Batching](#batching)
- [Copying streams](#copying-streams)
- [Framing](#framing)
- [Reading files](#reading-files)
- [mmap](#mmap)

## Buffering

Unbuffered small writes are one syscall each:

```go
f, _ := os.Create("out.txt")
for _, line := range lines {
    f.WriteString(line + "\n")   // one write(2) per line
}
```

Buffered writes accumulate in user space and cross once per buffer fill:

```go
f, err := os.Create("out.txt")
if err != nil {
    return err
}
defer f.Close()

w := bufio.NewWriter(f)
for _, line := range lines {
    w.WriteString(line)
    w.WriteByte('\n')
}
return w.Flush()   // without this, the tail is silently lost
```

For a large number of small lines this is routinely an order of magnitude
faster. It also avoids the `line + "\n"` allocation — two writes beat a
concatenation.

`bufio.Writer` does **not** flush on close of the underlying file. The
missing `Flush()` is the most common bufio bug, and it fails silently: the
data that fits in the buffer just never appears. `defer` the flush *and*
check its error, since a deferred `Flush` whose error is discarded can hide a
full disk.

Reading is symmetrical. `bufio.Scanner` for lines (note the default 64 KB
token limit — `Buffer()` raises it), `bufio.Reader` for everything else.

**When not to buffer:** interactive output where the user needs to see
progress, protocols where the peer waits for your response before continuing
(buffering there is a deadlock, not a slowdown), and anything where a crash
losing the buffer contents is unacceptable.

## Buffer sizing

`bufio` defaults to 4 KB, which matches the typical page size and filesystem
block size — a sensible default that fits most HTTP headers and small
payloads.

Larger buffers (16–64 KB) help for sustained streaming of large files or
high-volume logging: fewer, larger syscalls. Beyond that, returns diminish
quickly and you're just holding memory. Per-connection buffers multiply by
connection count — 64 KB read + 64 KB write across 10,000 connections is
1.3 GB, which is a memory decision disguised as a performance one.

Smaller buffers reduce latency-to-first-byte and memory footprint at the cost
of more syscalls. Right for interactive tools and low-connection-count,
latency-sensitive paths.

There is no correct number in the abstract. Measure syscall count
(`strace -c`, or `perf`) and throughput at a few sizes under realistic load,
and take the knee.

## Batching

The same principle applied above the syscall layer: to databases, RPCs, and
remote APIs, where the fixed cost per operation is a round trip rather than a
mode switch.

```go
// N round trips.
for _, e := range events {
    db.Exec("INSERT INTO events (id, data) VALUES ($1, $2)", e.ID, e.Data)
}

// One.
tx, err := db.Begin()
if err != nil {
    return err
}
stmt, err := tx.Prepare(pq.CopyIn("events", "id", "data"))
// ... feed rows, then commit
```

A generic size-triggered batcher:

```go
type Batcher[T any] struct {
    mu    sync.Mutex
    buf   []T
    size  int
    flush func([]T)
}

func NewBatcher[T any](size int, flush func([]T)) *Batcher[T] {
    return &Batcher[T]{buf: make([]T, 0, size), size: size, flush: flush}
}

func (b *Batcher[T]) Add(item T) {
    b.mu.Lock()
    defer b.mu.Unlock()
    b.buf = append(b.buf, item)
    if len(b.buf) >= b.size {
        b.flushLocked()
    }
}

func (b *Batcher[T]) Flush() {
    b.mu.Lock()
    defer b.mu.Unlock()
    b.flushLocked()
}

func (b *Batcher[T]) flushLocked() {
    if len(b.buf) == 0 {
        return
    }
    b.flush(b.buf)
    b.buf = b.buf[:0]
}
```

Three things this deliberately gets right, and that hand-rolled batchers
usually get wrong:

- **`flush` must not call `Add`.** Go mutexes are not reentrant; that
  deadlocks. If the flush function needs to re-enqueue failures, hand it a
  copy and let it route them elsewhere.
- **`b.buf[:0]` reuses the backing array**, so steady-state allocation is
  zero. But it also means `flush` must not retain the slice past its call —
  copy inside `flush` if it does.
- **A size trigger alone starves the tail.** In production you also want a
  time trigger (a `time.Ticker` calling `Flush`) so the last few items in a
  quiet period aren't held indefinitely, and a `Flush` on shutdown.

**The cost of batching is data loss on crash.** Anything in the buffer when
the process dies is gone. For transactional or critical data, either flush
synchronously on the critical path or write to durable storage before
acknowledging. Batching latency is also real: an item can wait up to a full
batch interval. If per-item latency is the SLO, batch smaller or not at all.

Batching also reduces allocations sharply — one large operation instead of
N small ones — which sometimes matters more than the syscall savings.

## Copying streams

```go
io.Copy(dst, src)                    // allocates a 32 KB buffer per call
io.CopyBuffer(dst, src, buf)         // reuses yours
```

For a server copying per request, `io.CopyBuffer` with a pooled buffer
eliminates that allocation:

```go
var copyBufPool = sync.Pool{
    New: func() any { b := make([]byte, 32*1024); return &b },
}

func proxy(dst io.Writer, src io.Reader) error {
    bp := copyBufPool.Get().(*[]byte)
    defer copyBufPool.Put(bp)
    _, err := io.CopyBuffer(dst, src, *bp)
    return err
}
```

Pool a `*[]byte`, not a `[]byte` — putting a slice into a `sync.Pool` boxes
the slice header into an interface and allocates on every `Put`, which
defeats the point.

Both `io.Copy` and `io.CopyBuffer` skip the buffer entirely when `src`
implements `io.WriterTo` or `dst` implements `io.ReaderFrom`. That's how
`net/http` gets `sendfile` for `*os.File` bodies — kernel-to-kernel with no
user-space copy at all. Don't wrap a `*os.File` in something that hides those
interfaces if you want that path.

## Framing

For length-prefixed protocols, naive `Read` loops fragment badly: a message
can span reads, and a read can contain several messages.

`bufio.Reader.Peek` inspects buffered bytes without consuming them, so you
can find a boundary before committing:

```go
r := bufio.NewReaderSize(conn, 8*1024)

for {
    hdr, err := r.Peek(4)              // look, don't consume
    if err != nil {
        return err
    }
    n := binary.BigEndian.Uint32(hdr)
    if n > maxFrame {
        return fmt.Errorf("frame too large: %d", n)   // always bound this
    }

    if _, err := r.Discard(4); err != nil {
        return err
    }
    payload := make([]byte, n)
    if _, err := io.ReadFull(r, payload); err != nil {
        return err
    }
    handle(payload)
}
```

The `maxFrame` check is not optional: an attacker-controlled length prefix
without a bound is a remote OOM.

If `handle` doesn't retain the payload, read into a reused buffer instead of
allocating per frame — but then `handle` must copy anything it keeps. That
tradeoff is the whole zero-copy question in miniature.

## Reading files

Match the API to the size and access pattern:

- `os.ReadFile` — whole file into memory, one allocation. Right for config
  and small files. Wrong for anything that could be large: memory usage
  equals file size. (Go 1.26 made `io.ReadAll` substantially cheaper, which
  helps the streaming-into-memory case too.)
- `bufio.Scanner` — line-oriented streaming, constant memory. Watch the
  64 KB default token limit.
- `bufio.Reader` — streaming with control over framing.
- `os.File.ReadAt` — random access without seeking; safe for concurrent use
  from multiple goroutines, unlike `Seek`+`Read`.

## mmap

Memory mapping is often called zero-copy. That's only half true, and the
distinction determines whether it helps you.

Mapping a file and then reading *out of it into your own buffer* still
copies. What you save is the per-call syscall: the pages are already mapped,
so reads are memory accesses rather than `pread` calls. Real, but modest —
this is syscall avoidance, not copy avoidance.

Mapping a file and operating **directly on the mapped pages** is actual
zero-copy: hash it, parse it, scan it in place, and the kernel-to-user copy
never happens.

```go
f, err := os.Open(path)
if err != nil {
    return err
}
defer f.Close()

fi, err := f.Stat()
if err != nil {
    return err
}

data, err := unix.Mmap(int(f.Fd()), 0, int(fi.Size()),
    unix.PROT_READ, unix.MAP_SHARED)
if err != nil {
    return err
}
defer unix.Munmap(data)

sum := xxhash.Sum64(data)   // no copy: reads the mapped pages directly
```

How much this wins depends entirely on what dominates:

- **Memory-bound work** (hashing with a fast hash, scanning, searching):
  removing a multi-megabyte copy from the critical path can roughly halve
  wall time.
- **Compute-bound work** (SHA-256, decompression, complex parsing): the copy
  was never the bottleneck. Expect a modest gain from reduced memory
  bandwidth pressure, nothing dramatic.

The costs are real: a page fault mid-access can block the OS thread (the
runtime cannot park a goroutine on a page fault the way it does for network
I/O), truncating a mapped file crashes the process with SIGBUS, mappings
consume address space, and it is platform-specific enough to complicate
builds. Note also that `golang.org/x/exp/mmap` does not expose the mapped
bytes — its `ReadAt` copies, so it gives you syscall avoidance only.

Use mmap for large, read-mostly, randomly-accessed files where you can work
in place — index files, embedded databases, large static datasets. For
sequential streaming, buffered reads are simpler and about as fast.
