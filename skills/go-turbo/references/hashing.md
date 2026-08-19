# Checksums and Hashing

Reuse a streaming hasher rather than allocating one per call, and pick the
function from whether you need speed, distribution, or collision resistance.

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
