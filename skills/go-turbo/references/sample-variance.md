# Samples and Variance

How many samples the claim needs, and what the spread has to look like before a
delta means anything.

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
