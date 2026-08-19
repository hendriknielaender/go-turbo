# Finding the Allocation

Locate the allocation before removing it. A profile names the site; code reading
names a suspicion.

## Find the allocation first

Use a benchmark to count per-operation churn and a profile to locate it:

```sh
go test ./path/to/pkg -run='^$' -bench='BenchmarkHot' -benchmem -count=10
go tool pprof -sample_index=alloc_objects http://localhost:6060/debug/pprof/allocs
go tool pprof -sample_index=alloc_space http://localhost:6060/debug/pprof/allocs
```

Object count finds allocator and GC churn; allocated bytes find large copies
and buffers. The allocation profile is sampled, so confirm a proposed fix in
the benchmark. Do not add pooling, aliasing, or `unsafe` from escape output
alone.

**Use when:** allocation appears in a representative profile or benchmark.
**Backfires when:** the benchmark omits the retaining consumer, concurrency,
or realistic input distribution and therefore rewards a lifetime bug.

## Version compatibility

`strings.Clone` requires Go 1.18 and `bytes.Clone` requires Go 1.20. For an
older supported module, force an owned byte copy with
`append([]byte(nil), src...)`; detach a retained string with
`string(append([]byte(nil), src...))` only when that lifetime boundary requires
it. Typed atomic values in layout examples also depend on the module's Go
version. Preserve the repository minimum and test allocation behavior with the
exact deployed compiler.
