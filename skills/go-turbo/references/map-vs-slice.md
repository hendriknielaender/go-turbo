# Map or Small Slice

Below a surprising size a linear scan beats a hash lookup, and the crossover is
worth knowing rather than guessing.

A map is the default for unbounded key lookup and uniqueness. A slice is often
the simpler representation for a small set that is mostly iterated, must keep
order, or is rebuilt as a unit. A linear slice scan has no hash computation
and reads contiguous memory; a map offers expected constant-time lookup but
has larger fixed costs and nondeterministic iteration order.

Do not encode a universal crossover point. Benchmark the real key type,
cardinality distribution, hit ratio, mutation pattern, and CPU architecture.
String hashing and integer comparison have different costs. A slice win at a
fixed size is invalid if production cardinality can grow without a hard cap.

```go
package lookup

type Entry struct {
	Key   uint32
	Value string
}

// Find is appropriate only while callers enforce a small maximum length.
func Find(entries []Entry, key uint32) (string, bool) {
	for i := range entries {
		if entries[i].Key == key {
			return entries[i].Value, true
		}
	}
	return "", false
}
```

Use a map when membership is the primary operation, deletes are common, or
the bound is not trustworthy. Use a sorted slice when updates are rare and
ordered iteration or range queries matter. Never depend on map iteration
order; sort keys explicitly when output must be stable.
