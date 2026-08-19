# JSON

JSON is the format most likely to sit on a hot path without anyone having chosen
it. Decode into typed structures, bound the input before you parse it, and
stream when the document is larger than the decision you need from it.

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
