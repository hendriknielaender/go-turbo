# Bounds-Check Elimination

The proofs the compiler can make, and the code shapes that let it.

The compiler normally eliminates checks in canonical loops:

```go
func sum(values []int) int {
	total := 0
	for i := 0; i < len(values); i++ {
		total += values[i]
	}
	return total
}
```

`range` is equally natural when the index is not needed. Choose the clearer
form and inspect BCE output only for a measured tight loop.

When several fixed offsets are accessed, one explicit proof can dominate later
checks:

```go
func decodeHeader(data []byte) (uint32, uint32) {
	_ = data[7]
	return binary.BigEndian.Uint32(data[:4]),
		binary.BigEndian.Uint32(data[4:8])
}
```

This preserves the same panic boundary while making the required length clear.
At trust boundaries, prefer an explicit length error rather than relying on a
panic:

```go
func decodeHeader(data []byte) (uint32, uint32, error) {
	if len(data) < 8 {
		return 0, 0, io.ErrUnexpectedEOF
	}
	return binary.BigEndian.Uint32(data[:4]),
		binary.BigEndian.Uint32(data[4:8]), nil
}
```

Loops indexing two independent slices often retain a check for the second
slice. Validate lengths once before the loop when the API requires them to
match. Never remove validation merely to remove a bounds check.

The payoff is usually tiny outside parsing, crypto, compression, numeric, and
codec loops. Require a benchmark before making code less direct.
