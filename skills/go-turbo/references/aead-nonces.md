# AEAD Nonce Safety

Nonce reuse under one key breaks the guarantee entirely. This is the one place
where a performance shortcut is a security bug, not a tradeoff.

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
