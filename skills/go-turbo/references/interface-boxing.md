# Interface Conversion and Boxing

Converting a value to an interface is not automatically an allocation, and the
cases where it is are specific enough to check rather than guess.

## Distinguish interface conversion from heap allocation

Putting a concrete value in an interface constructs an interface value. It
allocates backing storage only when the concrete data must escape its current
storage or another operation around the conversion allocates. Verify with
`-gcflags=-m=2` and `allocs/op`; do not equate every box with a heap object.

An escaping interface collection can make large value copies expensive:

```go
type Shape interface {
	Area() float64
}

func retain(dst []Shape, squares []Square) []Shape {
	for i := range squares {
		dst = append(dst, &squares[i])
	}
	return dst
}
```

Use `&squares[i]`, not `&square`, when identity must refer to the slice
element. The pointer form avoids copying a large value into interface storage,
but it retains the entire `squares` backing array, permits mutation through
aliases, adds indirection, and may move data to the heap. For small immutable
values, storing the value is often faster and simpler.

At an internal hot boundary with a stable type, a concrete function or a
generic helper can enable static dispatch. Keep interfaces where runtime
polymorphism, package boundaries, or testability justify them; compiler
devirtualization may already remove the indirect call.

**Use concrete or pointer forms when:** profiles attribute material copy,
dispatch, or escape cost to the interface path. **Backfires when:** the change
weakens the abstraction, retains a large owner, increases generated generic
code, or trades a cheap value copy for pointer chasing and GC scan work.
