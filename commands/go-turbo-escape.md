---
description: Heap escape audit — map every escape to its cause and fix
argument-hint: "[package or path]"
---

Run the `go-turbo-escape` skill on: $ARGUMENTS

Run `go build -gcflags='-m=2'`, narrow to paths relevant to the workload, and
classify each escape as incidental or required by lifetime. A non-inlined call
does not itself imply escape. Verify impact with allocations and benchmarks;
compiler diagnostics explain cause, not cost.
