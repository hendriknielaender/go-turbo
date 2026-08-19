# Strings and Bytes

Pick one representation and stay in it. Round-tripping `string` and `[]byte`
copies every time, and repeated concatenation reallocates — both are among the
most common avoidable allocations in Go.

## Keep text in one representation

Ordinary `string(bytes)` and `[]byte(text)` conversions preserve value
semantics by copying data. Carry `[]byte` through parsing and I/O code, or
carry `string` through text code, instead of converting at every layer:

```go
func isRequestLine(line []byte) bool {
	return bytes.HasPrefix(line, []byte("GET "))
}
```

The compiler can use the byte slice transiently without a copy for a direct
string comparison, map lookup, or map deletion:

```go
if string(token) == "ready" {
	consume(token)
}

value, ok := table[string(token)]
delete(table, string(token))
```

That is a compiler optimization, not permission to retain mutable bytes as a
string. A map insertion must preserve the key after the byte slice changes,
so this conversion copies:

```go
table[string(token)] = value
```

Do not replace safe conversions with `unsafe.String` or `unsafe.Slice` unless
a profile proves the copy matters and the API can enforce immutability and
lifetime. A single mutation, append, pool return, or early reclamation can
turn the optimization into corrupted keys, races, or dangling data.

**Use one representation when:** adjacent layers already accept it and the
ownership contract stays simple. **Backfires when:** forcing `[]byte` through
text-oriented APIs spreads mutable aliasing, or conversion avoidance couples
otherwise clean package boundaries. Recheck on the deployed toolchain; these
elisions are not language guarantees.

## Build strings once

Repeated `+=` in a loop repeatedly copies the prefix. Use a builder and grow
it from a realistic size estimate:

```go
func join(parts []string, estimate int) string {
	var b strings.Builder
	if estimate > 0 {
		b.Grow(estimate)
	}
	for _, part := range parts {
		b.WriteString(part)
	}
	return b.String()
}
```

`strings.Builder.String` exposes the built bytes as an immutable string
without a final copy. Never copy a non-zero `Builder`. Use `bytes.Buffer`
instead when the consumer needs `[]byte`, `io.Reader`, or `io.Writer`
behavior.

**Use when:** several fragments form one retained string. **Backfires when:**
the estimate substantially overstates normal output, one concatenation would
already be clear and cheap, or callers need mutable bytes and immediately
convert the result back.
