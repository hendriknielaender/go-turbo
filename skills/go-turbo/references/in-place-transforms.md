# In-Place Transforms

Filtering and compacting through the same backing array, valid when the input is
yours to modify.

In-place compaction can remove an allocation when the caller owns the slice
and no alias needs the original contents. It is not a free win if mutation
breaks caller expectations or if retained elements keep large object graphs
alive. When elements contain pointers, clear positions beyond the returned
length so stale references in the backing array do not extend lifetimes.

```go
package compact

// KeepNonEmpty compacts values in place. The caller must own values and use
// the returned slice. Clearing the tail drops stale string-data references.
func KeepNonEmpty(values []string) []string {
	write := 0
	for _, value := range values {
		if value == "" {
			continue
		}
		values[write] = value
		write++
	}
	clear(values[write:])
	return values[:write]
}
```

`clear` removes references from the discarded slice positions; it does not
erase the bytes referenced by a string, force immediate reclamation, or affect
references held elsewhere. Another alias of the same backing array can still
observe the in-place writes, which is why exclusive ownership is part of the
function contract. The `clear` built-in requires Go 1.21; on an older supported
toolchain, assign the element type's zero value in a loop over the tail.

If input and output lifetimes differ, allocating a right-sized result can
retain less memory than returning a small subslice of a large backing array.
Choose ownership clarity first, then compare allocations and live heap.
