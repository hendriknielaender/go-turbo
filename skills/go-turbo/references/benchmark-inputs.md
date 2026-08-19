# Deterministic Inputs

A benchmark that generates its own input differently each run measures the
generator. Warm and cold cases are separate questions.

## Deterministic benchmark inputs

Use the same bytes and operation order under both toolchains. Seeded input is
not necessarily reproducible if the generator implementation itself differs
between versions. Prefer a checked-in corpus, or use a tiny generator whose
algorithm is owned by the benchmark and tested with a fixed digest.

```go
package toolchainbench

import (
	"hash/crc32"
	"testing"
)

var checksumSink uint32

func deterministicCorpus(seed uint64, count, size int) [][]byte {
	if seed == 0 {
		panic("seed must be nonzero")
	}
	corpus := make([][]byte, count)
	state := seed
	for i := range corpus {
		item := make([]byte, size)
		for j := range item {
			state ^= state << 13
			state ^= state >> 7
			state ^= state << 17
			item[j] = byte(state)
		}
		corpus[i] = item
	}
	return corpus
}

func BenchmarkChecksum(b *testing.B) {
	corpus := deterministicCorpus(0x6a09e667f3bcc909, 64, 4096)
	table := crc32.MakeTable(crc32.Castagnoli)
	b.ReportAllocs()
	b.ResetTimer()
	var sum uint32
	for i := 0; i < b.N; i++ {
		for _, item := range corpus {
			sum ^= crc32.Checksum(item, table)
		}
	}
	checksumSink = sum
}
```

Use benchmark APIs accepted by the oldest evaluated toolchain. `B.Loop` is
available starting in Go 1.24; a comparison that includes an older release
must use the `b.N` shape above or keep version-selected benchmark files with
identical workloads. A build failure is not a benchmark sample.

Generate fixtures outside the timed region. Verify counts and sizes, and avoid
all-zero data unless production is all zeros. For randomized property tests,
print the seed on failure. For performance comparisons, preserve the exact
corpus so both toolchains see identical branch and cache behavior.

Separate benchmarks by meaningful production dimensions rather than averaging
small and large payloads into one opaque number. Keep setup and teardown out of
the timed region unless lifecycle cost is the subject of the benchmark.

## Warm and cold cases

"Cold" must name which cache is cold:

- an empty Go build cache for compile-time evaluation;
- a fresh process with no application caches;
- an empty connection pool or TLS session state;
- data absent from the filesystem page cache;
- a freshly initialized JIT in a dependency, if any.

Do not claim all caches are cold after clearing only one. Purging the host page
cache is privileged, disruptive, and usually inappropriate on a shared
machine. A fresh process and isolated build-cache directory are safer,
repeatable definitions. If true machine-cold behavior matters, use dedicated
hosts and document the reset procedure.

Warm benchmarks should include an explicit warm-up that is not recorded, then
measure a long enough steady interval to expose GC and scheduler cycles. Cold
start and steady state answer different questions; retain both rather than
letting warm iterations hide startup work.

For build performance, give each toolchain its own initially empty cache
directory for cold runs, then repeat using that same directory for warm runs.
Do not let the target toolchain inherit artifacts populated by the baseline.
