# Binary Encoding

A binary format is a compatibility contract before it is a performance choice.
Append into a caller's buffer rather than returning a fresh one.

## Binary encoding

Binary formats are justified by an existing protocol, strict payload budgets,
or measured codec cost. They trade human readability and schema flexibility
for compact fixed-width fields. Always specify byte order, field widths,
maximum lengths, optional-field rules, and version negotiation.

For fixed-size values, `encoding/binary.Append` grows a destination, so it does
not fail merely because the existing capacity is too small. It can still
return an error when the value is unsupported. `encoding/binary.Encode` never
grows its caller-provided buffer and returns an error when that buffer is too
small or the value is unsupported. Propagate either API's error.

```go
package wirebinary

import (
	"encoding/binary"
	"errors"
)

type Header struct {
	Kind   uint16
	Flags  uint16
	Length uint32
}

func AppendHeader(dst []byte, h Header) ([]byte, error) {
	return binary.Append(dst, binary.BigEndian, h)
}

func EncodeHeader(dst []byte, h Header) ([]byte, error) {
	size := binary.Size(h)
	if size < 0 {
		return nil, errors.New("unsupported header type")
	}
	if len(dst) < size {
		return nil, errors.New("header destination too small")
	}
	n, err := binary.Encode(dst[:size], binary.BigEndian, h)
	if err != nil {
		return nil, err
	}
	return dst[:n], nil
}
```

For `encoding/binary`, a fixed-size struct contains only supported fixed-size
scalars (`bool`, fixed-width integers, floating-point numbers, or complex
numbers), arrays, or structs. Fields are encoded successively in declaration
order; Go's in-memory alignment padding is not emitted. A blank (`_`) field
encodes as zero-valued bytes of its encoded size and is skipped on decode, so
it can represent explicit wire padding. Every non-blank field in a struct used
as a decode destination must be exported; decoding into an unexported field may
panic. Use exported fields for a type shared by encoding and decoding.

Do not treat an in-memory struct as wire bytes with `unsafe`. That couples the
protocol to architecture, alignment, and representation details and can expose
padding.

For two or three integer fields, explicit `ByteOrder.PutUint32` calls can be
clearer and may avoid reflective work. That is a paid micro-optimization:
benchmark the complete encode/decode path before duplicating schema logic.
Reject declared lengths before allocation and check integer conversions on
32-bit targets.

`binary.Append` was added in Go 1.23. On an older supported toolchain, compute
`binary.Size` and use `binary.Write` with a bounded buffer, or encode a small
fixed schema explicitly with `ByteOrder.PutUint*`. `binary.Encode` was also
added in Go 1.23, so it is not an older-version fallback. Propagate every
write error and test identical wire bytes across implementations.

## Measurement and correctness gates

Benchmark with production payload distributions, not one friendly document.
Report throughput or latency together with bytes and allocations per operation.
Include malformed, maximum-size, and incompressible cases outside the timed
benchmark as correctness and resource tests.

Before shipping a representation change:

1. Preserve wire compatibility or version the protocol deliberately.
2. Fuzz decoders with hard byte, item, and recursion limits.
3. Compare round trips against canonical test vectors.
4. Profile the whole request path; copying, I/O, and validation may dominate.
5. Treat every cryptographic optimization as a security review item.

Keep the typed, bounded, standard-library implementation when measurements do
not separate alternatives reliably.
