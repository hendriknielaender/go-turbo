# go-turbo

Performance rules for Go in this repository. Portable across agents that read
`AGENTS.md`. Full detail lives in `skills/go-turbo/SKILL.md` and its
`references/`.

## Stance

Write Go the way a staff performance engineer would: allocation-aware
idiomatic Go by default, restructured for speed only where a measurement says
it matters. Fast Go and idiomatic Go are usually the same code. When they
diverge, say so and let the number decide.

## The ladder

Work top-down. Stop when the cost stops justifying the complexity.

1. Does the work need to happen at all?
2. Is the algorithm and data structure right? (Nothing below rescues a bad
   complexity class.)
3. Does it allocate on the hot path?
4. Does it escape when it doesn't have to?
5. Does it cross an expensive boundary per item — syscall, round trip, query,
   lock?
6. Does it contend?
7. Only then: memory layout, false sharing, inlining, `unsafe`, SIMD.

## Free wins — apply while writing, no profile needed

- `make([]T, 0, n)` / `make(map[K]V, n)` when `n` is known or boundable
- `strings.Builder` with `Grow` instead of `+=` in a loop
- `bufio` around any file or socket touched more than once
- struct fields ordered widest-first
- `copy` into a right-sized slice before handing a sub-slice of a big buffer
  to anything that may retain it
- stay in `[]byte` rather than round-tripping through `string`
- `sync.OnceValue` over hand-rolled init flags
- reuse compiled regexps, templates, and `time.Location` values

## Paid wins — need a profile or benchmark first

`sync.Pool`, zero-copy slice sharing, lock-free structures, `unsafe`, manual
layout, GC tuning. Each one ships with a comment naming what was traded:

```go
// turbo: pooled 32 KB buffers; caller must not retain past Handle().
// Drop the pool if allocation stops showing in profiles.
```

## Evidence discipline

- No profile, no paid win. Free wins and algorithmic fixes are always fair.
- Benchmark with `-benchmem -count=10`, compare with `benchstat`. One run is
  a sample of size one.
- Report `allocs/op` alongside `ns/op`. It's the more stable number and it
  usually explains the other.
- If you can't measure, say which rung you applied and what would need
  measuring to go further.

## Never trade these for speed

Race freedom (`-race` on any concurrency change), error handling, context
propagation and cancellation, input validation at trust boundaries, deadlines
on network I/O, and readability when the payoff is unmeasured.

## Let Go be Go

Over-preallocation is not free. `append` is well tuned. Pointers are not
automatically cheaper than values. The compiler already inlines, eliminates
dead code, and removes redundant bounds checks. C and C++ habits applied
verbatim frequently make Go slower.

## Output

Code first, then at most: one line per non-obvious change, the measurement
(or an explicit note that there isn't one), and the next rung you'd climb.
No essays defending optimizations.
