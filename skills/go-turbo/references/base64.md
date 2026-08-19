# Base64 and Text Encodings

Output length is a known function of input length, so the destination can always
be sized exactly.

## Base64 and other text encodings

For one in-memory value, append-oriented encoding can reuse a caller-owned
destination. `AppendEncode` cannot report malformed input because every byte
sequence has a Base64 representation. `AppendDecode` can fail and returns the
bytes decoded before the error; a record-oriented caller should discard that
partial suffix rather than process it.

```go
package textwire

import (
	"encoding/base64"
	"fmt"
)

func AppendBase64(dst, src []byte) []byte {
	return base64.StdEncoding.AppendEncode(dst, src)
}

func AppendDecodedBase64(dst, src []byte) ([]byte, error) {
	out, err := base64.StdEncoding.AppendDecode(dst, src)
	if err != nil {
		// AppendDecode can expose a partial record. Clear the appended region
		// and return the caller's original slice on failure.
		clear(out[len(dst):])
		return dst, fmt.Errorf("decode base64: %w", err)
	}
	return out, nil
}
```

The returned successful slice may share `dst`'s backing array. The caller owns
that storage and must copy before handing a long-lived result to code that may
mutate or retain the buffer. Do not overlap `src` with append capacity in `dst`:
the API does not promise overlap safety. If canonical encodings matter, select
the exact alphabet and padding policy deliberately. `Strict` additionally
requires zero trailing padding bits, but even strict decoding ignores CR and
LF; reject those separately when the application grammar forbids them.

For streams, `base64.NewEncoder` must be closed and its `Close` error propagated
to flush a final partial block. Decoder errors arrive from reads. Put byte and
time limits around the underlying stream. `AppendEncode` and `AppendDecode`
were added in Go 1.22; older toolchains can extend by the checked `EncodedLen`
or `DecodedLen` and call `Encode` or `Decode` into that region, applying the
same discard-on-decode-error rule.
