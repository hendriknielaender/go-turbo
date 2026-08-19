# Compression

Compression trades CPU for bytes on the wire, and the ratio depends entirely on
the payload. Reuse writers and readers rather than constructing them per
message, and bound decompressed output before you produce it.

Compression saves bandwidth at the cost of CPU, latency, and memory. It can
expand small or already-compressed input. Decide by content type and measured
size distribution, and negotiate the algorithm explicitly.

Every compression writer has a finalization contract. For gzip, `Close` flushes
pending bytes and writes the footer; it does not close the destination. A
successful `Write` followed by a dropped `Close` error can produce a truncated
stream while the caller reports success.

```go
package compressed

import (
	"compress/gzip"
	"io"
)

func WriteGZIP(dst io.Writer, src []byte) error {
	zw := gzip.NewWriter(dst)
	if _, err := zw.Write(src); err != nil {
		// Preserve the write error. This instance is not eligible for reuse.
		_ = zw.Close()
		return err
	}
	return zw.Close()
}
```

Reusing a compressor with `Reset` or pooling it is a paid optimization. First
show construction or allocation in a profile. A writer may be reset or returned
to a pool only after all writes and `Close` succeeded; `Reset` before `Close`
discards unfinished state, and an instance that observed either error should be
discarded. Never let callers retain pooled buffers, cap retained object sizes,
and document the compression level because ratio and CPU are coupled.

Decompression is a trust boundary. Bound compressed bytes, expanded bytes,
nesting or archive entry counts, and total processing time. A small compressed
payload can expand dramatically. Verify checksums and authentication in the
protocol-defined order; compression combined with secrets and attacker-
controlled plaintext may also leak information through output length.

```go
package compressed

import (
	"bytes"
	"compress/gzip"
	"errors"
	"fmt"
	"io"
	"math"
)

func ReadGZIP(src []byte, maxCompressed, maxExpanded int64) (out []byte, err error) {
	if maxCompressed < 1 || maxExpanded < 1 || maxExpanded == math.MaxInt64 {
		return nil, errors.New("invalid compressed or expanded byte limit")
	}
	if int64(len(src)) > maxCompressed {
		return nil, errors.New("compressed input exceeds limit")
	}

	zr, err := gzip.NewReader(bytes.NewReader(src))
	if err != nil {
		return nil, fmt.Errorf("open gzip stream: %w", err)
	}
	defer func() {
		if closeErr := zr.Close(); err == nil && closeErr != nil {
			err = fmt.Errorf("close gzip stream: %w", closeErr)
		}
	}()

	out, err = io.ReadAll(io.LimitReader(zr, maxExpanded+1))
	if err != nil {
		return nil, fmt.Errorf("read gzip stream: %w", err)
	}
	if int64(len(out)) > maxExpanded {
		return nil, errors.New("expanded data exceeds limit")
	}
	// ReadAll reached io.EOF, so gzip verified the footer checksum.
	return out, nil
}
```

The `maxExpanded+1` sentinel is safe only after rejecting `math.MaxInt64`.
Returning on the first byte beyond the bound deliberately rejects the member
without draining it. For an unbounded network reader, independently limit the
compressed side before gzip sees it and use a context or deadline; an expanded
byte cap alone does not bound time spent receiving input.
