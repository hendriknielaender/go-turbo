# Profile-Guided Optimization

A representative, current profile is the whole input. A stale one optimises last
quarter's traffic.

PGO lets the compiler use a CPU profile to prioritize hot call edges and make
more aggressive inlining/devirtualization choices. It is a low-code-change
option, not a reason to skip application profiling.

Place a representative profile named `default.pgo` in the main package
directory, or pass a profile explicitly:

```sh
go build -pgo=./profiles/service.pprof -o service ./cmd/service
go build -pgo=off -o service-nopgo ./cmd/service
```

Compare PGO on and off with the workload and binary that matter. Keep these
rules:

- collect from a representative mix, not a single synthetic endpoint;
- do not publish profiles containing sensitive symbol or path information
  without review;
- retain the exact profile used for reproducible release builds;
- refresh it when call paths or workloads change materially;
- verify binary size, startup, CPU, and tail latency rather than assuming every
  metric improves;
- test each target architecture separately.

A stale profile is usually tolerated, but “usually” is not an acceptance test.
