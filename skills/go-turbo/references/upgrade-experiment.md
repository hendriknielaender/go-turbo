# Designing an Upgrade Experiment

Comparing two Go releases is an experiment, and it is only as good as its
controls. Fix the contract before collecting a sample.

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
