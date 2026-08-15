# Encoding, Text, Hashing, and Compression

Representation choices affect CPU, allocations, wire size, and failure modes.
Choose the simplest format that satisfies the compatibility contract, impose
input bounds before decoding, and optimize only the codec that profiles show
on the hot path.

## Contents

- [Typed JSON](#typed-json)
- [Streaming JSON](#streaming-json)
- [Binary encoding](#binary-encoding)
- [Base64 and other text encodings](#base64-and-other-text-encodings)
- [Append-oriented number formatting](#append-oriented-number-formatting)
- [Regular expressions](#regular-expressions)
- [Checksums, hashes, and cryptography](#checksums-hashes-and-cryptography)
- [AEAD nonce safety](#aead-nonce-safety)
- [Compression](#compression)
- [Measurement and correctness gates](#measurement-and-correctness-gates)

## Typed JSON

Decode stable schemas into structs. Typed fields document the wire contract,
remove dynamic type assertions from application code, and make validation
explicit. They do not promise an allocation-free codec: `encoding/json` uses
reflection and may allocate or box values internally. Compare `B/op` and
`allocs/op` before claiming that a typed representation is cheaper.
`map[string]any` remains appropriate for truly dynamic documents, proxies that
preserve unknown fields, and exploratory tooling; it should not be the default
for a known request type.

Bound bytes before decoding. A decoder is not a substitute for a request-size
limit, and deeply nested or extremely large valid input can exhaust resources.

```go
package wirejson

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
)

type Request struct {
	AccountID string   `json:"account_id"`
	Scores    []int64  `json:"scores"`
	Labels    []string `json:"labels,omitempty"`
}

func DecodeOne(r io.Reader, maxBytes int64) (Request, error) {
	if maxBytes < 1 || maxBytes == math.MaxInt64 {
		return Request{}, errors.New("maxBytes must be in [1, math.MaxInt64)")
	}
	data, err := io.ReadAll(io.LimitReader(r, maxBytes+1))
	if err != nil {
		return Request{}, err
	}
	if int64(len(data)) > maxBytes {
		return Request{}, errors.New("JSON document exceeds limit")
	}

	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	var req Request
	if err := dec.Decode(&req); err != nil {
		return Request{}, fmt.Errorf("decode request: %w", err)
	}
	// A decoder accepts a stream. Requiring EOF after the first value rejects
	// a second JSON document as well as malformed trailing non-space bytes.
	var extra struct{}
	if err := dec.Decode(&extra); err != io.EOF {
		if err == nil {
			return Request{}, errors.New("expected exactly one JSON document")
		}
		return Request{}, fmt.Errorf("decode trailing JSON: %w", err)
	}
	if req.AccountID == "" {
		return Request{}, errors.New("account_id is required")
	}
	return req, nil
}
```

`json.Unmarshal` also rejects trailing non-space content. When a service uses
`json.Decoder` for one document, the first successful `Decode` is not enough:
call `Decode` again and require exactly `io.EOF`, as above. Use
`DisallowUnknownFields` only when unknown keys are client errors; it can break
forward-compatible storage and proxy formats. If exact numeric text matters,
use `json.Number` or a typed integer rather than routing numbers through
`float64`.

Use `json.RawMessage` to defer decoding a bounded nested value. Its
`UnmarshalJSON` method copies the encoded value into the RawMessage. By
contrast, a manual conversion such as `json.RawMessage(buf[start:end])`
aliases `buf`; clone that view before it outlives or crosses ownership of the
source buffer.

## Streaming JSON

Streaming reduces peak memory when the format contains a sequence of values
or a large array that can be consumed incrementally. It does not make input
unbounded: wrap the reader in an application limit and separately cap item
count, nesting expectations, and decoded collection lengths.

Decoder calls may read ahead. Do not mix direct reads from the underlying
reader with decoder reads without accounting for `Decoder.Buffered`. An
incremental callback may have side effects before a later item fails; if the
operation must be atomic, stage changes or buffer the bounded document first.

`Encoder.Encode` appends a newline. That is useful for JSON Lines and can be a
wire incompatibility elsewhere. `Marshal` produces one byte slice and is often
simpler for small responses. Measure both in the actual handler, including
socket writes and buffer retention.

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

## Append-oriented number formatting

When building a byte-oriented record, keep it in bytes. `strconv.AppendInt`,
`AppendUint`, `AppendFloat`, and `AppendBool` append directly to an existing
slice and avoid an intermediate formatted string. Preallocate only when a
reasonable upper bound is known.

```go
package record

import "strconv"

func AppendMetric(dst []byte, name string, value int64, valid bool) []byte {
	dst = append(dst, name...)
	dst = append(dst, '=')
	dst = strconv.AppendInt(dst, value, 10)
	dst = append(dst, ' ')
	dst = strconv.AppendBool(dst, valid)
	dst = append(dst, '\n')
	return dst
}
```

Use `Format*` when the API naturally needs a string; converting the final byte
slice back to a string can erase the allocation win. Confirm with `allocs/op`
and test negative values, bases, precision, infinities, and NaNs where relevant.

## Regular expressions

Compile a constant pattern once, usually at package initialization. A compiled
`*regexp.Regexp` is safe for concurrent matching. Use its `Match` method on
`[]byte` input to avoid a byte-to-string conversion when the rest of the path
is already byte-oriented.

Prefer `strings` or `bytes` operations for a fixed prefix, delimiter, or exact
token. They state the intent better and often do less work. Keep a regular
expression when it materially improves correctness for a genuine pattern;
hand-written parsers accumulate edge cases quickly.

Go's regular-expression engine avoids catastrophic exponential backtracking,
but matching still consumes resources proportional to input and pattern work.
Limit attacker-controlled input before matching. Compile user-provided
patterns at a controlled boundary, reject invalid patterns, and budget their
storage instead of compiling on every request.

Benchmarks must include matches, misses, short inputs, and the long tail. A
fast success at byte zero says little about a failure that scans the entire
payload.

## Checksums, hashes, and cryptography

Choose by security property, not benchmark rank:

- A CRC detects accidental transmission or storage corruption. It does not
  resist an attacker who can change both data and checksum.
- A fast non-cryptographic hash is suitable for in-process tables,
  partitioning, or deduplication where collisions are handled. It is not a
  signature and should not become a permanent protocol identifier casually.
- A cryptographic digest such as SHA-256 provides collision resistance for
  content identification, but an unkeyed digest does not authenticate a
  message.
- HMAC authenticates data shared by parties holding the secret key. Compare
  authenticators with constant-time library operations.
- AEAD provides confidentiality and integrity together. Authentication
  failure must discard plaintext and remain indistinguishable to callers.
- Password storage needs a deliberately expensive password KDF with recorded
  parameters, not a fast general-purpose digest.

Standard-library implementations are the default. Hardware acceleration and
architecture change relative throughput, so benchmark only among algorithms
that satisfy the required security and interoperability contract. Never weaken
the property to gain throughput without a protocol-level security review.

Use a one-shot function when the whole value is already in memory, and a
`hash.Hash` when data arrives incrementally. `Sum` appends the digest without
changing the running state. `Reset` returns that state to its initial value; it
does not make a mutable hasher safe for concurrent goroutines.

```go
package digest

import (
	"crypto/sha256"
	"io"
)

func Bytes(data []byte) [sha256.Size]byte {
	return sha256.Sum256(data)
}

func Reader(r io.Reader) ([sha256.Size]byte, error) {
	h := sha256.New()
	if _, err := io.Copy(h, r); err != nil {
		return [sha256.Size]byte{}, err
	}
	var sum [sha256.Size]byte
	encoded := h.Sum(sum[:0])
	copy(sum[:], encoded)
	return sum, nil
}
```

The streaming helper intentionally inherits the reader's lifetime. At a trust
boundary, put an input byte cap and cancellation or deadline around `r`; a
streaming hash does not make unlimited work safe.

Choose stability deliberately. A persisted content identifier or wire value
needs a named, versioned algorithm whose output is stable across processes.
`hash/maphash` instead uses a randomized seed and is intended for in-process
hashing, including adversarial keys; do not persist its output. A `maphash.Hash`
is not concurrency-safe. To share one seed within a process, give each
goroutine its own `Hash` and call `SetSeed` with the common `Seed`.

Reuse a streaming hasher only under exclusive ownership: consume `Sum`, call
`Reset`, and do not expose it concurrently. `Sum(dst)` may reuse `dst`'s
backing array; the returned digest follows that slice's ownership and does not
alias the mutable hash state. Pooling hashers adds mutable ownership and can
retain input fragments in internal state, so require a profile and avoid
cross-tenant reuse for secret data. For HMAC, keep key ownership explicit,
reuse only with the same key, and compare tags with `hmac.Equal`.

## AEAD nonce safety

Reusing a nonce with the same AEAD key can destroy confidentiality and
authenticity. With AES-GCM on Go 1.24 and later, prefer
`cipher.NewGCMWithRandomNonce`. It generates and prepends a 96-bit nonce during
`Seal`, extracts it during `Open`, reports `NonceSize() == 0`, and requires a
zero-length nonce argument (conventionally `nil`). The documented safety bound
is no more than 2^32 encrypted messages for one key, aggregated across every
process and lifetime using it.

The following wrapper enforces that bound only because its constructor requires
a fresh key for which this instance is the sole encryption authority. Peers may
decrypt with the key; a bidirectional protocol should derive a key per
direction. The mutex keeps the quota and AEAD access under one ownership rule.
Do not copy the returned value.

```go
package securewire

import (
	"crypto/aes"
	"crypto/cipher"
	"errors"
	"sync"
)

const maxMessagesPerKey uint64 = 1 << 32

type RecordCipher struct {
	mu       sync.Mutex
	aead     cipher.AEAD
	messages uint64
}

// NewRecordCipher requires freshKey to be newly generated and all encryption
// under that key to pass through the returned RecordCipher. A persistent or
// multi-writer key needs a durable aggregate counter outside this process.
func NewRecordCipher(freshKey []byte) (*RecordCipher, error) {
	block, err := aes.NewCipher(freshKey)
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCMWithRandomNonce(block)
	if err != nil {
		return nil, err
	}
	return &RecordCipher{aead: aead}, nil
}

func (c *RecordCipher) Seal(plaintext, additionalData []byte) ([]byte, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.messages == maxMessagesPerKey {
		return nil, errors.New("GCM message limit reached; rotate key")
	}
	c.messages++
	return c.aead.Seal(nil, nil, plaintext, additionalData), nil
}

func (c *RecordCipher) Open(ciphertext, additionalData []byte) ([]byte, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	// A nil destination keeps failed authentication from exposing a caller's
	// partially overwritten destination buffer.
	return c.aead.Open(nil, nil, ciphertext, additionalData)
}
```

In a service that reloads or shares a key, the in-memory count above is not
enough. The key authority must count all encryptions durably and rotate before
the aggregate limit; retries must not bypass that authority. For any other
nonce construction, require a reviewed durable protocol covering replica
assignment, restarts, rollback, snapshots, counter exhaustion, and key
rotation. Do not substitute a process-local counter and random prefix.

Pass exactly the same additional data to `Open`, and release no plaintext when
authentication fails. `AEAD.Open` may overwrite a supplied destination's
capacity even on failure, which is why the example uses a nil destination.
`NewGCMWithRandomNonce` was added in Go 1.24. On an older toolchain, prefer an
upgrade; otherwise use a reviewed protocol or library that owns nonce
generation, transmission, and the aggregate per-key limit.

## Compression

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
