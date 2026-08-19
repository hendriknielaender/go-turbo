# Stream Copies

`io.Copy` and friends already take the fast path where one exists. Reimplementing
the copy usually loses it.

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
