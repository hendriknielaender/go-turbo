# go-turbo-bench

## What it does

`go-turbo-bench` writes a Go benchmark you can trust, runs it properly, and
reads the result honestly.

It assumes the benchmark is wrong until it is guarded. Most Go benchmarks
measure something other than what their author intended, in four classic ways:
the compiler deleted the work, setup got timed, the input was unrepresentative,
or one run was compared against one run and noise was reported as a win. Most of
what this skill does is closing those four holes — which is why it treats
`b.ReportAllocs()` as mandatory and `-count=10` as the minimum for any
comparison.

## When to reach for it

Type `/go-turbo-bench` — the agent will not fire it on its own. Pass a function
or a package.

Reach for it when you need evidence: before optimising, to establish a baseline;
after, to defend the result; or when a benchmark you already have is telling you
something you do not believe.

## Reading the result

A benchstat comparison is read as a set, not as a percentage:

| What you look at | What it tells you |
| --- | --- |
| The comparison marker | `~` means the samples do not distinguish the versions — "no measurable change in this experiment," which is not "identical" |
| Spread relative to the effect | Large overlap means the experiment lacks resolution; find the noise before trusting a small delta |
| `ns/op`, `B/op`, `allocs/op` together | A detectable change can still be operationally irrelevant |

`B/op` and `allocs/op` are near-deterministic and usually explain the `ns/op`
movement, which is why allocation reporting is not optional here. And a stated
speedup carries its conditions: "34% faster on 1 KB inputs, n=10, on this
machine" is a claim; "34% faster" is marketing.

The traps it watches for are concrete — sub-nanosecond `ns/op` means the
compiler deleted the work; a benchmark that improved while the service did not
means the function was never the bottleneck; a short benchmark may never trigger
a collection, hiding the GC cost of the allocations it makes.

## Common questions

**Why does it benchmark several input sizes instead of one?**

Because throughput changes non-linearly as you cross cache levels, and a single
average hides exactly the transition you care about. It builds size
sub-benchmarks by default and adds `b.SetBytes` so you get MB/s alongside.

**My mutex-protected structure benchmarks fine.**

A single-goroutine benchmark measures the uncontended fast path, which is not
the case anyone was worried about. Contention needs `b.RunParallel`, and the
skill will add it rather than let the uncontended number stand as the answer.

## It's working if

- Setup sits outside the timed region, and `b.ReportAllocs()` is always there.
- More than one input size appears, unless there is a reason only one exists.
- Comparisons run at `-count=10` or more, with `-run=^$`.
- The reported result includes the machine, the input distribution, and what the
  benchmark does not cover.
- A `~` result is reported as no measurable change rather than quietly dropped.

## Where it fits

A reach-for-it-anytime standalone that also supplies the evidence the chain runs
on: [go-turbo-analyze](go-turbo-analyze.md) uses it when no measurement exists
yet, and [go-turbo-improve](go-turbo-improve.md) uses it on both sides of a fix.
For profiling and load testing rather than benchmarks, that material lives in the
`pprof.md` and `load-testing.md` references. [go-turbo-help](go-turbo-help.md) routes the whole set.
