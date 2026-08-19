# Pooling

`sync.Pool` buys allocation reduction with a lifetime contract that outlives
whoever added it. It needs a measured churn problem first.

## Pool only proven temporary churn

Use `sync.Pool` for temporary, independently reusable objects shared across
many concurrent calls. Treat every `Get` as a cache miss: the runtime may
remove any pooled value at any time without notification.

```go
var bufferPool = sync.Pool{
	New: func() any { return new(bytes.Buffer) },
}

func encodeResponse(w io.Writer, v Value) error {
	b := bufferPool.Get().(*bytes.Buffer)
	b.Reset()
	defer func() {
		if b.Cap() <= 64<<10 {
			b.Reset()
			bufferPool.Put(b)
		}
	}()

	if err := encode(b, v); err != nil {
		return err
	}
	_, err := w.Write(b.Bytes())
	return err
}
```

Choose the retention cap from observed size percentiles and the service memory
budget; `64<<10` is only an example. Reset all logical state before reuse, and
clear sensitive bytes when confidentiality requires it. Nothing returned by
the operation may reference pooled storage after `Put`.

**Use when:** a profile shows repeated construction of similar temporary
objects under sustained concurrent load and a benchmark includes misses and
parallel use. **Backfires when:** objects are cheap, traffic is sparse, sizes
have outliers, cleanup has ownership semantics, callers retain aliases, or the
pool is mistaken for a cache with availability guarantees. Never copy a Pool
after first use.
