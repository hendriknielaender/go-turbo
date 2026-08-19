# Inlining and Devirtualization

The cost model and the constructs that block it, both of which move between Go
releases.

Inlining removes a call boundary and exposes more code to constant propagation,
escape analysis, and bounds-check elimination. The compiler uses a cost model
that changes between releases. Avoid memorizing a fixed budget or a permanent
list of blockers.

```sh
go build -gcflags='-m -m' ./pkg 2>&1 | rg 'inline|devirtual'
```

Non-inlined calls do not imply that pointer arguments escape. The compiler
exports escape summaries across many call boundaries. Read the actual escape
diagnostic.

Interface calls and function values inhibit ordinary direct-call inlining, but
the compiler can sometimes devirtualize when it proves the concrete target;
PGO can provide additional hot-call evidence. Check the selected toolchain's
output instead of assuming either outcome.

When a measured function is too large to inline, keep a small common path and
move rare work behind a helper:

```go
func (c *Cache) Get(key string) (Value, bool) {
	if value, ok := c.hot[key]; ok {
		return value, true
	}
	return c.getSlow(key)
}
```

Use this shape only when it remains clear and a benchmark shows a benefit.
Splitting code can add branches, duplicate checks, and worsen instruction-cache
behavior.

`//go:noinline` is useful for controlled compiler experiments. It is rarely a
production optimization and should not be left behind without measured need.
