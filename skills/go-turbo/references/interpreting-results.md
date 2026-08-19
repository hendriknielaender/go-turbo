# Interpreting Results

What the comparison supports, and the canary and rollback gates that stay open
regardless.

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
