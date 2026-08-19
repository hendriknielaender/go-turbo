# Same-Host Comparison

Two toolchains, one machine, one session, interleaved. Anything else measures
the environment.

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
