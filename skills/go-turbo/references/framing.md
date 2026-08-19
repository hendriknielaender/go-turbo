# Defensive Framing

A length prefix you have not bounded is an allocation an attacker chooses.

## Frame streams defensively

TCP is a byte stream: a `Read` can return part of a frame or several frames.
Use a bounded framing format and `io.ReadFull` for fixed-width pieces.

```go
func readFrame(r *bufio.Reader, maxFrame int) ([]byte, error) {
	if maxFrame < 0 {
		return nil, fmt.Errorf("negative frame limit: %d", maxFrame)
	}
	header, err := r.Peek(4)
	if err != nil {
		return nil, err
	}
	encodedSize := binary.BigEndian.Uint32(header)
	if uint64(encodedSize) > uint64(maxFrame) {
		return nil, fmt.Errorf(
			"frame size %d exceeds limit %d",
			encodedSize,
			maxFrame,
		)
	}
	if _, err := r.Discard(4); err != nil {
		return nil, err
	}

	payload := make([]byte, int(encodedSize))
	if _, err := io.ReadFull(r, payload); err != nil {
		return nil, err
	}
	return payload, nil
}
```

Set a read deadline at the connection layer so a peer cannot reserve the
declared frame forever. Validate the length before conversion or allocation.
When reusing a payload buffer, document that the handler may not retain it; copy
only the portion that crosses into a longer lifetime.

`Peek` and methods such as `ReadSlice` return views into the reader's buffer.
Those bytes are invalidated by later reads. This is useful for synchronous
parsing and unsafe for asynchronous handoff without a copy.
