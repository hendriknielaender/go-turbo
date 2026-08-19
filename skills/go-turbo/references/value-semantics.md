# Values and Stack Scratch

Return `T` instead of `*T` where identity and nil are not part of the contract,
and use a bounded array for small fixed scratch.

## Prefer values when values express the semantics

Return and pass small immutable structs by value unless mutation, identity, or
nil has meaning:

```go
func parseHeader(src []byte) (Header, error) {
	var h Header
	if err := decodeHeader(&h, src); err != nil {
		return Header{}, err
	}
	return h, nil
}
```

Registers and stack copies often make this cheaper than allocating a separate
object and chasing a pointer. The compiler may remove copies entirely.

**Use when:** the type is modest, copy semantics are correct, and benchmarks
show pointer construction or GC pressure. **Backfires when:** the struct is
large or copied frequently, contains synchronization primitives that must not
be copied, requires stable identity, or value semantics obscure mutation.

## Use bounded stack scratch deliberately

For a small protocol maximum, use a local array and slice it:

```go
func appendNumber(dst []byte, n int64) []byte {
	var scratch [32]byte
	tmp := strconv.AppendInt(scratch[:0], n, 10)
	return append(dst, tmp...)
}
```

The returned `dst` owns the copied bytes; the local scratch does not escape.
Prefer this shape only when the bound is inherent and the compiler is not
already producing an equivalent stack path.

**Use when:** a fixed small maximum is part of the format and a benchmark
removes a hot allocation. **Backfires when:** large arrays increase stack
growth and copying, recursion multiplies frame cost, the bound is guessed, or
the resulting slice escapes and moves the array to the heap anyway.
