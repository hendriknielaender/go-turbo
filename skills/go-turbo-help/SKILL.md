---
name: go-turbo-help
description: >
  Quick-reference card for all go-turbo modes, skills, and commands.
  One-shot display, not a persistent mode. Trigger: /go-turbo-help,
  "go-turbo help", "what go-turbo commands", "how do I use go-turbo",
  "go turbo cheatsheet".
license: MIT
---

# go-turbo Help

Display this card when invoked. One-shot: do NOT change mode, write files, or
persist anything.

## Levels

| Level | Trigger | What changes |
|-------|---------|--------------|
| **cruise** | `/go-turbo cruise` | Clean idiomatic Go. Free wins applied silently, paid wins named in one line for the user to choose. Nothing restructured. |
| **turbo** | `/go-turbo` | The ladder enforced. Hot paths checked for allocation and escape; paid wins applied where evidence supports them. Default. |
| **redline** | `/go-turbo redline` | Every hot-path allocation is a defect. `unsafe`, manual layout, syscall tuning, lock-free structures on the table — each with a benchmark in the same response. |

Level sticks until changed or session end.

## Skills

| Skill | Trigger | What it does |
|-------|---------|--------------|
| **go-turbo** | `/go-turbo` | The mode itself. Writes and reviews Go like a staff performance engineer. |
| **go-turbo-analyze** | `/go-turbo-analyze` | Diagnose why it's slow. Ranked, evidence-backed. Changes nothing. |
| **go-turbo-improve** | `/go-turbo-improve` | Apply the fix and prove it with `benchstat`. |
| **go-turbo-escape** | `/go-turbo-escape` | Heap escape audit via `-gcflags=-m`, with the restructure for each. |
| **go-turbo-bench** | `/go-turbo-bench` | Write benchmarks that measure the right thing; read them honestly. |
| **go-turbo-review** | `/go-turbo-review` | Performance review of a diff. `L42: alloc: append into nil slice. make(…, 0, len(rows)).` |
| **go-turbo-audit** | `/go-turbo-audit` | Whole-repo ranked performance hotlist + measurement coverage. |
| **go-turbo-help** | `/go-turbo-help` | This card. |

Typical flow: `/go-turbo-analyze` → `/go-turbo-improve` → `/go-turbo-bench`.

## The ladder

Work top-down; stop when the cost stops justifying the complexity.

1. Does the work need to happen at all?
2. Is the algorithm and data structure right?
3. Does it allocate on the hot path?
4. Does it escape when it doesn't have to?
5. Does it cross an expensive boundary per item?
6. Does it contend?
7. Only then: layout, false sharing, inlining, `unsafe`, SIMD.

## Free wins vs paid wins

**Free** — apply while writing, no profile needed: `make` with capacity,
`strings.Builder`, `bufio`, widest-first field order, copy before handing off
a sub-slice, stay in `[]byte`, `sync.OnceValue`, reuse compiled regexps.

**Paid** — need evidence first, and a `turbo:` comment saying what was
traded: `sync.Pool`, zero-copy sharing, lock-free structures, `unsafe`,
manual layout, GC tuning.

```go
// turbo: pooled 32 KB buffers; caller must not retain past Handle().
// Drop the pool if allocation stops showing in profiles.
```

## Commands worth memorizing

```sh
go test -bench=. -benchmem -count=10 -run=^$ ./pkg > old.txt
benchstat old.txt new.txt

go build -gcflags=-m ./... 2>&1 | grep -E 'escapes to heap|moved to heap'

go tool pprof -http=:8080 http://localhost:6060/debug/pprof/profile?seconds=30
go tool pprof -http=:8080 http://localhost:6060/debug/pprof/allocs
go tool pprof -http=:8080 -base=heap1.out heap2.out

GODEBUG=gctrace=1 ./service
go tool trace trace.out

curl -o default.pgo 'http://prod:6060/debug/pprof/profile?seconds=60'  # then just build
```

## Reference files

Under `skills/go-turbo/references/`:

`allocation.md` · `escape-analysis.md` · `gc-and-runtime.md` ·
`concurrency.md` · `io-and-syscalls.md` · `networking.md` ·
`measurement.md` · `compiler.md`

## Deactivate

Say "stop go-turbo" or "normal mode". Resume with `/go-turbo`.
`/go-turbo off` also works.

## The rule that matters

No profile, no paid win. Free wins are always fair; everything else needs a
number. Fast is a property you measure, not a style you adopt.
