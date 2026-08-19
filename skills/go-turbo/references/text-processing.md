# Text Processing

Formatting and matching are the two text costs that show up in hot loops.
Append-oriented formatting keeps the result in a caller's buffer, and a compiled
regexp is a value to reuse rather than rebuild.

## Append-oriented number formatting

When building a byte-oriented record, keep it in bytes. `strconv.AppendInt`,
`AppendUint`, `AppendFloat`, and `AppendBool` append directly to an existing
slice and avoid an intermediate formatted string. Preallocate only when a
reasonable upper bound is known.

```go
package record

import "strconv"

func AppendMetric(dst []byte, name string, value int64, valid bool) []byte {
	dst = append(dst, name...)
	dst = append(dst, '=')
	dst = strconv.AppendInt(dst, value, 10)
	dst = append(dst, ' ')
	dst = strconv.AppendBool(dst, valid)
	dst = append(dst, '\n')
	return dst
}
```

Use `Format*` when the API naturally needs a string; converting the final byte
slice back to a string can erase the allocation win. Confirm with `allocs/op`
and test negative values, bases, precision, infinities, and NaNs where relevant.

## Regular expressions

Compile a constant pattern once, usually at package initialization. A compiled
`*regexp.Regexp` is safe for concurrent matching. Use its `Match` method on
`[]byte` input to avoid a byte-to-string conversion when the rest of the path
is already byte-oriented.

Prefer `strings` or `bytes` operations for a fixed prefix, delimiter, or exact
token. They state the intent better and often do less work. Keep a regular
expression when it materially improves correctness for a genuine pattern;
hand-written parsers accumulate edge cases quickly.

Go's regular-expression engine avoids catastrophic exponential backtracking,
but matching still consumes resources proportional to input and pattern work.
Limit attacker-controlled input before matching. Compile user-provided
patterns at a controlled boundary, reject invalid patterns, and budget their
storage instead of compiling on every request.

Benchmarks must include matches, misses, short inputs, and the long tail. A
fast success at byte zero says little about a failure that scans the entire
payload.
