# Pointer Density

Pointer-rich structures cost on every collection. Value-dense layouts do not.

The garbage collector scans pointers, not arbitrary bytes. Pointer-rich
graphs also scatter accesses across cache lines. Prefer compact values and
contiguous slices when ownership permits. Keep large immutable payloads out
of per-item metadata, and consider separating hot fields from rarely used
diagnostic fields when profiles show cache or heap pressure.

Field ordering changes padding. For private structs, descending alignment or
width is a good first layout because it often removes holes; inspect the actual
size on each supported architecture. Do not blindly reorder public structs:
positional composite literals in other packages can break, serialized output
or binary layouts may depend on order, and atomic fields can have alignment
requirements. Group fields by
access pattern when cache locality matters more than minimum total size.
Pointer compression, structure-of-arrays layouts, and manual padding are paid
optimizations; they need benchmark or profile evidence and a comment naming
the maintenance tradeoff.

Values are not automatically cheaper than pointers. Copying a large struct
through a hot call chain can cost more than one well-owned pointer, while a
pointer per tiny element can multiply allocations. Let escape analysis,
`allocs/op`, and live-heap profiles decide.
