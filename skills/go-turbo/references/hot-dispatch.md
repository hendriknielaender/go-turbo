# Hot Dispatch and Inlining

Concrete types at hot internal boundaries, and the coupling between inlining and
escape analysis that makes the two evidence for each other.

## Keep hot dispatch visible when evidence supports it

A concrete internal helper can expose callee behavior and static dispatch:

```go
func writeBatch(w *bufio.Writer, records []Record) error {
	for _, record := range records {
		if _, err := w.WriteString(record.Name); err != nil {
			return err
		}
	}
	return nil
}
```

Keep an interface at the public boundary and adapt once outside the hot loop
when the concrete implementation is truly fixed. A generic helper is another
option, but it can increase build time and binary size and does not guarantee
inlining.

**Use when:** a profile shows indirect-call or escape cost and the internal
type is stable. **Backfires when:** it couples packages, duplicates paths for
several implementations, or the compiler already devirtualizes the call.

## Treat inlining and escape analysis as coupled evidence

Inlining can expose caller-specific lifetimes and constant values; escape
summaries can preserve useful facts even when a call is not inlined. Ask the
compiler what happened:

```sh
go build -gcflags='-m=2' ./path/to/pkg 2>&1 | rg 'inline|escape|heap'
```

If a hot wrapper is not inlined, keep its common path small and move uncommon
error or setup work into a helper. Do not depend on a fixed compiler budget or
assume a particular statement is always an inlining blocker.

**Use when:** profiles show a very frequent call and diagnostics connect
inlining to a real allocation or dispatch cost. **Backfires when:** splitting
fragments cohesive logic, grows code and instruction-cache pressure, or PGO
and a newer toolchain already make the desired decision.
