# Experiments and Low-Level Code

`GOEXPERIMENT`, assembly, and SIMD: measured, gated, and fenced behind a portable
fallback.

Record active experiments and inspect the selected compiler instead of copying
flags from another release. Consult that toolchain's release notes and source
for the supported experiment names:

```sh
go env GOEXPERIMENT
go tool compile -help
```

Compiler experiments, runtime experiments, `unsafe`, SIMD packages, and
assembly are evidence-gated. For each:

- keep a correct portable baseline;
- benchmark representative sizes and architectures;
- run differential/property/fuzz tests;
- run the race detector where supported;
- document alignment, aliasing, CPU-feature, and lifetime assumptions;
- provide a removal trigger and a fallback for unsupported toolchains.

Do not use `unsafe.String` or `unsafe.Slice` merely to remove a conversion. The
resulting alias and lifetime contract is often more expensive than the copy and
can turn immutable strings into mutable shared state.
