---
description: Heap escape audit — map every escape to its cause and fix
argument-hint: "[package or path]"
---

Run the `go-turbo-escape` skill on: $ARGUMENTS

Run `go build -gcflags=-m`, narrow to hot paths, classify each escape as incidental (fixable by code shape) or necessary (the value genuinely outlives the frame), and give the concrete restructure for the incidental ones. Verify with allocs/op, not with `-m` output.
