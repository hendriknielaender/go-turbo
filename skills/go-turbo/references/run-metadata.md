# Run Metadata

A result without its commit, toolchain, host, and configuration is not
reproducible and not a claim.

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
