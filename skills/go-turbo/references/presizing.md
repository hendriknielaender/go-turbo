# Presizing Slices and Maps

Size from a bound you can defend. An exact or representative capacity avoids the
growth copies; an untrusted maximum is a denial-of-service vector.

## Preallocate known work

Give slices capacity when the expected result count is known or tightly
bounded:

```go
func convertAll(rows []Row) []Result {
	results := make([]Result, 0, len(rows))
	for _, row := range rows {
		results = append(results, convert(row))
	}
	return results
}
```

Allocate the final length and assign by index when every output slot is
written exactly once:

```go
func convertAll(rows []Row) []Result {
	results := make([]Result, len(rows))
	for i, row := range rows {
		results[i] = convert(row)
	}
	return results
}
```

Use a map hint for a credible entry count:

```go
index := make(map[string]int, len(keys))
```

The map argument is an initial-size hint, not a capacity contract. Its effect
depends on key/value sizes and the current map implementation.

**Use when:** the bound is cheap to obtain and close to typical occupancy.
**Backfires when:** the bound is an adversarial or rare maximum, the result is
usually filtered down, or `make([]T, n)` is followed by `append` and silently
leaves `n` zero values at the front.

## Let slices and maps grow when size is uncertain

`append` uses an implementation-defined growth policy coordinated with
allocator size classes. Growth allocates a new backing array and copies the
old elements only when capacity is exhausted. Do not encode current growth
thresholds into application logic.

For untrusted or highly variable input, start small or cap the initial hint:

```go
const initialLimit = 1024

hint := len(rows)
if hint > initialLimit {
	hint = initialLimit
}
results := make([]Result, 0, hint)
```

**Use explicit capacity when:** a stable cardinality removes repeated growth
from a hot path. **Let growth work when:** the distribution has a long tail or
the collection is small. Manual growth can waste memory, copy more, and become
wrong as runtime behavior changes.
