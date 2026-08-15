# Evaluating Go Toolchain Upgrades

A toolchain upgrade is a code change even when the source tree is identical.
It can alter generated machine code, escape decisions, runtime scheduling,
garbage collection, standard-library behavior, binary size, and diagnostics.
Treat every claimed speedup or regression as a hypothesis until reproduced on
the application and deployment platforms.

## Contents

- [Discover the evaluation matrix](#discover-the-evaluation-matrix)
- [Correctness before speed](#correctness-before-speed)
- [Write the experiment contract](#write-the-experiment-contract)
- [Deterministic benchmark inputs](#deterministic-benchmark-inputs)
- [Warm and cold cases](#warm-and-cold-cases)
- [Same-host sequential comparison](#same-host-sequential-comparison)
- [Samples, variance, and reliability](#samples-variance-and-reliability)
- [Capture complete metadata](#capture-complete-metadata)
- [Interpret results](#interpret-results)
- [Production validation and rollback](#production-validation-and-rollback)

## Discover the evaluation matrix

Determine the versions and platforms from the repository and deployment; do
not inherit an authoring machine's toolchain as policy. Record the main
module's `go` and `toolchain` directives, CI/release configuration, supported
deployment targets, and the exact requested upgrade. Resolve ambiguous or
conflicting sources with the repository owner before measuring.

Before qualifying a production candidate, verify from the official Go release
history and security announcements that the exact patch is still an intended,
supported target. A superseded patch may remain useful for regression
isolation, but it is not automatically the right artifact to deploy.

Run every command through the exact binary being evaluated:

```sh
GOTOOLCHAIN=local /absolute/path/to/baseline/go version
GOTOOLCHAIN=local /absolute/path/to/baseline/go env -json
GOTOOLCHAIN=local /absolute/path/to/candidate/go version
GOTOOLCHAIN=local /absolute/path/to/candidate/go env -json
```

`GOTOOLCHAIN=local` prevents a `toolchain` directive or automatic selection
from silently replacing the binary being tested. Confirm the version printed
by every artifact and benchmark process.

Run performance binaries natively on every material production architecture.
Cross-compilation proves only that the target builds. Never compare labels
such as "old" and "new" without exact patch versions and artifact identities.

## Correctness before speed

Before collecting performance data with the target toolchain:

1. Build every shipped command and test binary with the production tags,
   cgo mode, linker flags, and generated sources.
2. Run unit, integration, fuzz-regression, and race tests appropriate to the
   change. A benchmark cannot validate semantics.
3. Review new compiler and static-analysis diagnostics rather than suppressing
   them to keep a clean log.
4. Exercise platform integrations, plugins, assembly, cgo, and reflection-
   heavy paths that may compile differently.
5. Confirm module and vendor state did not change between toolchains unless
   dependency changes are intentionally part of the experiment.

Keep source, dependencies, environment, and workload fixed. If source edits
are required for compatibility, benchmark those edits under both toolchains
where possible so compiler effects are not confused with source effects.

## Write the experiment contract

Decide before looking at results:

- exact baseline and target toolchain versions;
- each native `GOOS/GOARCH` deployment pair;
- benchmark names, payload distributions, concurrency, and duration;
- primary metrics and acceptable regression budgets;
- whether cold start, steady state, compilation, or all three matter;
- sample count, noise policy, and criteria for rerunning;
- functional gates and rollback conditions.

These budgets are product and operational decisions. Do not invent universal
percentage thresholds. When they are missing, characterize ordinary variance
and current capacity headroom, recommend a detectable decision boundary, and
ask the owner to approve it before interpreting the comparison as a release
gate.

Use application benchmarks first. Standard-library microbenchmarks can help
locate a change but cannot tell how often the application calls that path.
Include `ns/op`, `B/op`, and `allocs/op`; add throughput, tail latency, live
heap, GC CPU, resident memory, binary size, or compile time when they represent
the production objective.

Do not infer a release-wide rule from one benchmark. A runtime optimization
may help pointer-heavy heaps and do nothing for a mostly stack-resident CLI.
A compiler change may shift an inline boundary in either direction. These are
investigation hypotheses, not version facts.

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

## Same-host sequential comparison

Run baseline and target sequentially on the same quiet host. Concurrent runs
compete for CPU, memory bandwidth, cache, and thermal headroom. Keep power
mode fixed, close unrelated workloads, and avoid shared CI runners for small
effects.

A representative steady-state command shape is:

```sh
# Run the exact baseline binary first and preserve raw output.
GOTOOLCHAIN=local /absolute/path/to/baseline/go test -run='^$' -bench=. -benchmem -count=20 ./... > baseline.txt

# Then run the exact candidate binary on the same checkout and host.
GOTOOLCHAIN=local /absolute/path/to/candidate/go test -run='^$' -bench=. -benchmem -count=20 ./... > candidate.txt

benchstat baseline.txt candidate.txt
```

Replace both example paths before execution and archive the expanded commands.
Capture `version` and `env` through those same exact binaries. Toolchain
downloads, module downloads, and compilation should finish before a runtime
microbenchmark comparison so network and setup do not pollute the timed
samples.

Sequential order can still bias a long suite through warming or thermal drift.
For a consequential result, repeat complete blocks in the reverse order or
alternate baseline/target blocks while keeping individual processes isolated.
Never interleave output in a way the comparison tool cannot identify.

## Samples, variance, and reliability

One measurement is reconnaissance. `go test -count=20` records twenty
benchmark measurements in one test-binary process; this is useful for a warm
steady-state comparison but does not provide process-independent or cold-start
samples. When process initialization, address layout, or per-process state is
part of the question, invoke each test binary in separate processes with a
small checked-in harness and archive every result. Twenty is a starting point,
not a universal requirement: fewer samples can reveal a large effect and more
may be needed for noisy workloads. Compare distributions with `benchstat`
rather than subtracting two means by hand.

Compute coefficient of variation as sample standard deviation divided by the
sample mean. It is a diagnostic, not a universal pass/fail number:

- low CV supports detecting smaller effects;
- high CV means scheduling, thermal state, setup, input, or workload phases
  may dominate;
- a claimed improvement smaller than ordinary variation is not established;
- near-zero or signed metrics need another reliability measure because CV is
  undefined or misleading.

Do not delete inconvenient outliers without a recorded external cause. Fix
the source of variance, lengthen the benchmark, isolate the host, or report the
result as inconclusive. Rerunning only until a favorable result appears is
selection bias.

Allocation counts are often more stable than time and can explain a timing
shift. A changed `allocs/op` deserves escape-analysis and heap-profile review;
unchanged allocations with a time change may point toward code generation,
runtime, cache behavior, or noise.

## Capture complete metadata

Store enough information to reproduce and reject invalid comparisons:

- repository commit, dirty-state indicator, module graph checksum, build tags,
  generated-code version, and benchmark corpus digest;
- complete `go version` and relevant `go env`, including `GOEXPERIMENT`, cgo,
  compiler and linker flags;
- OS release, kernel, architecture, CPU model and count, memory, virtualization,
  container limits, and power or frequency policy;
- benchmark command, start time, duration, sample count, environment variables,
  and working directory;
- background load, temperature or throttling evidence when available, and
  whether the host was dedicated;
- raw benchmark output, comparison output, profiles, and test results.

At minimum, capture these commands through each exact toolchain beside the
results:

```sh
GOTOOLCHAIN=local /absolute/path/to/baseline/go version
GOTOOLCHAIN=local /absolute/path/to/baseline/go env -json
GOTOOLCHAIN=local /absolute/path/to/candidate/go version
GOTOOLCHAIN=local /absolute/path/to/candidate/go env -json
uname -a
git rev-parse HEAD
git status --short
```

Secrets may appear in environment output. Capture a deliberate allowlist for
shared artifacts or redact before publishing; reproducibility never justifies
leaking credentials.

## Interpret results

Classify each result as improvement, regression, or inconclusive using the
predeclared metric and noise policy. Explain production relevance in absolute
terms: saved CPU cores at expected throughput, startup time on a real command,
or added bytes per live request. A large percentage on an irrelevant
nanobenchmark is not an upgrade decision.

When a regression appears:

1. Reproduce it on the same host and corpus.
2. Narrow it to runtime, standard library, generated code, or compiler output
   using profiles and focused benchmarks.
3. Confirm source and dependencies are truly identical.
4. Test the native deployment architecture; code generation is architecture-
   specific.
5. Reduce to a small reproducer only after the application effect is proven.

Release notes and compiler diagnostics can suggest mechanisms, but they do not
replace measurement. A result for one exact patch release does not
automatically apply to another. Record the exact binary used.

## Production validation and rollback

Microbenchmarks are the first gate, not the last. Build target-toolchain
artifacts in the normal supply chain, canary them under representative traffic,
and compare service-level latency, error rate, CPU, memory, GC, connection
behavior, and correctness signals. Keep workload routing comparable and allow
enough time to cover periodic jobs and heap cycles.

Predefine rollback triggers and retain a known-good baseline artifact. A
toolchain can pass unit tests and improve throughput while changing memory
peaks, crash diagnostics, or rare scheduling behavior. Expand rollout only
when both correctness and capacity evidence hold on every supported production
platform.

If the environment cannot be controlled well enough for a reliable result,
say so. The honest conclusion is "no measured decision yet," followed by the
specific host, sample, or production evidence needed to close the gate.
