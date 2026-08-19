# Raw TCP and Framing

Below HTTP you own framing, and every frame you agree to read needs a bound
before you allocate for it.

## Raw TCP and bounded framing

TCP is an ordered byte stream. A `Read` does not correspond to a peer `Write`:
it may return a partial header, combine messages, or split a payload. Define
framing explicitly. A length prefix is simple when the receiver validates the
length before allocating.

```go
package frame

import (
	"encoding/binary"
	"errors"
	"io"
)

const MaxPayload = 1 << 20

var ErrFrameTooLarge = errors.New("frame exceeds maximum payload")

func Read(r io.Reader) ([]byte, error) {
	var header [4]byte
	n, err := io.ReadFull(r, header[:])
	if err != nil {
		// EOF before any header byte is a clean boundary between frames.
		// ReadFull reports a partial header as ErrUnexpectedEOF.
		if n == 0 && errors.Is(err, io.EOF) {
			return nil, io.EOF
		}
		return nil, err
	}
	size := binary.BigEndian.Uint32(header[:])
	if size > MaxPayload {
		return nil, ErrFrameTooLarge
	}
	payload := make([]byte, int(size))
	if _, err := io.ReadFull(r, payload); err != nil {
		// Once a non-empty payload has been advertised, even an EOF before
		// its first byte is a truncated frame rather than a clean shutdown.
		if errors.Is(err, io.EOF) {
			return nil, io.ErrUnexpectedEOF
		}
		return nil, err
	}
	return payload, nil
}

func Write(w io.Writer, payload []byte) error {
	if len(payload) > MaxPayload {
		return ErrFrameTooLarge
	}
	var header [4]byte
	binary.BigEndian.PutUint32(header[:], uint32(len(payload)))
	if err := writeAll(w, header[:]); err != nil {
		return err
	}
	return writeAll(w, payload)
}

func writeAll(w io.Writer, p []byte) error {
	for len(p) != 0 {
		n, err := w.Write(p)
		if err != nil {
			return err
		}
		if n == 0 {
			return io.ErrNoProgress
		}
		p = p[n:]
	}
	return nil
}
```

The example permits an empty payload and caps every non-empty payload at one
application-defined limit. A real protocol should also define version,
message kind, authentication, unknown-field behavior, and whether multiple
frames form one transaction. Check length arithmetic before converting or
adding header sizes.

Set read and write deadlines around protocol phases. A context does not by
itself interrupt an arbitrary `net.Conn` read; arrange cancellation by setting
a deadline or closing the connection. Treat EOF between frames differently
from EOF inside a frame. A truncated frame is a protocol error, not a clean
shutdown.

Buffering helps when the application performs many small operations. It can
hurt when a flush is forgotten or adds latency to an already large write.
Make flush boundaries part of the protocol and measure syscall counts.
