<h1 align="center">go-turbo</h1>

<p align="center">
  <em>Go performance mode for AI coding agents.</em><br>
  <strong>Fast is a property you measure, not a style you adopt.</strong>
</p>

---

Most AI-generated Go is correct and quietly wasteful: `append` into a nil
slice when the length was right there, a `[]byte` → `string` → `[]byte` round
trip per request, `go handleItem(x)` over an unbounded queue, a response body
closed but never drained so connections are never reused.

The reflex fix is worse. Ask for "optimized Go" and you get `sync.Pool` on a
cold path, `unsafe` with no benchmark, `GOGC` set from a blog post, and a
function nobody can read that was never the bottleneck.

**go-turbo installs the third option:** the reflexes of a staff performance
engineer. Allocation-aware idiomatic Go by default. A ladder worked
top-down. Cheap optimizations applied silently; expensive ones only where a
measurement justifies them, and always labeled.

## Install

**Claude Code**

```
/plugin marketplace add hendriknielaender/go-turbo
/plugin install go-turbo
```

**Everything else** — copy the rules file your agent reads:

| Agent | File |
|-------|------|
| Claude Code, Codex, Amp, and other `AGENTS.md` readers | `AGENTS.md` |
| Cursor | `.cursor/rules/go-turbo.mdc` |

Or drop `skills/` into any agent that loads Anthropic-style skills.

## Commands

| Command | What it does |
|---------|--------------|
| `/go-turbo [cruise\|turbo\|redline]` | Turn the mode on and set intensity |
| `/go-turbo-analyze` | Diagnose why it's slow. Ranked, evidence-backed, changes nothing |
| `/go-turbo-improve` | Apply the fix and prove it with `benchstat` |
| `/go-turbo-escape` | Heap escape audit via `-gcflags=-m`, with the restructure for each |
| `/go-turbo-bench` | Write benchmarks that measure the right thing |
| `/go-turbo-review` | Performance review of a diff, one line per finding |
| `/go-turbo-audit` | Whole-repo ranked hotlist plus measurement coverage |
| `/go-turbo-help` | Reference card |

Typical flow: `/go-turbo-analyze` → `/go-turbo-improve` → `/go-turbo-bench`.

## The ladder

Every performance decision goes through this, top-down. Stop when the cost
stops justifying the complexity — the rungs are ordered by
payoff-per-unit-of-ugliness.

1. **Does the work need to happen at all?** The fastest code is the call you
   deleted.
2. **Is the algorithm right?** O(n²) → O(n) beats every allocation trick
   combined. Nothing below rescues a bad complexity class.
3. **Does it allocate on the hot path?** Allocation is paid twice — once at
   the allocator, again at every GC mark.
4. **Does it escape?** `-gcflags=-m`. Stack values are free to collect.
5. **Does it cross an expensive boundary per item?** Syscalls, round trips,
   queries, locks. Buffer or batch.
6. **Does it contend?** Contention doesn't show up until load, and then it's
   a cliff.
7. **Only then:** layout, false sharing, inlining, `unsafe`, SIMD.

## Free wins vs paid wins

This distinction is the whole design.

**Free wins** cost nothing in readability, so they're applied while writing —
no profile required:

```go
out := make([]Result, 0, len(rows))   // not: var out []Result
var b strings.Builder                 // not: s += part in a loop
w := bufio.NewWriter(f)               // not: f.Write per line
data := make([]byte, n); copy(data, buf[:n])   // not: queue <- buf[:n]
```

**Paid wins** buy speed with complexity, lifetime rules, or unsafety. They
need evidence first and a comment saying what was traded:

```go
// turbo: pooled 32 KB buffers; caller must not retain the slice past
// Handle(). Drop the pool if allocation stops showing in profiles.
```

`sync.Pool`, zero-copy slice sharing, lock-free structures, `unsafe`, manual
layout, GC tuning — all paid. The rule is short: **no profile, no paid win.**

## Intensity

| Level | What changes |
|-------|--------------|
| **cruise** | Clean idiomatic Go. Free wins silently, paid wins named in one line for you to choose. Nothing restructured. |
| **turbo** | The ladder enforced. Hot paths checked for allocation and escape; paid wins where evidence supports them. **Default.** |
| **redline** | Every hot-path allocation is a defect. `unsafe`, manual layout, syscall tuning on the table — each with a benchmark in the same response. |

`/go-turbo cruise` · `/go-turbo` · `/go-turbo redline`. Level persists until
changed.

## What it will not do

Correctness beats throughput; a fast wrong answer is a bug with good latency.
go-turbo never trades away:

- race freedom — `-race` runs on any concurrency change
- error handling, or context propagation and cancellation
- input validation at trust boundaries
- deadlines on network I/O
- readability, when the payoff is unmeasured

It also pushes back on the other failure mode. A `sync.Pool` on a cold path
gets flagged as a finding in review, not praised as an optimization.

## Knowledge base

The skill ships a catalog covering the mechanism, the fix, and the conditions
under which the fix backfires:

| Reference | Covers |
|-----------|--------|
| `allocation.md` | Preallocation, `sync.Pool`, interface boxing, struct layout, false sharing, string/`[]byte`, zero-copy, retained backing arrays |
| `escape-analysis.md` | Reading `-gcflags=-m`, what forces heap allocation, restructures, when escaping is correct, inlining |
| `gc-and-runtime.md` | Collector mechanics, `GOGC`, `GOMEMLIMIT`, weak pointers, `GOMAXPROCS`, scheduler, netpoller |
| `concurrency.md` | Worker pools and sizing, atomics vs mutexes, sharding, immutable snapshots, context, goroutine leaks, backpressure |
| `io-and-syscalls.md` | Buffering, batching, `io.CopyBuffer`, framing, file reads, `mmap` |
| `networking.md` | `http.Transport`/`Server` tuning, connection reuse, TLS, DNS, socket options, long-lived connections |
| `measurement.md` | Benchmarks that measure the right thing, `benchstat`, `pprof`, tracing, load testing, what benchmarks don't tell you |
| `compiler.md` | Build flags, inlining, bounds-check elimination, PGO, cgo cost, `GOEXPERIMENT` |

Current as of Go 1.26 — Green Tea GC, `b.Loop()`, `weak`,
`net.KeepAliveConfig`, container-aware `GOMAXPROCS`, PGO.

## Layout

```
go-turbo/
├── AGENTS.md                       portable always-on rules
├── commands/                       slash commands
├── skills/
│   ├── go-turbo/
│   │   ├── SKILL.md                the mode
│   │   └── references/             the knowledge base
│   ├── go-turbo-analyze/
│   ├── go-turbo-improve/
│   ├── go-turbo-escape/
│   ├── go-turbo-bench/
│   ├── go-turbo-review/
│   ├── go-turbo-audit/
│   └── go-turbo-help/
├── .claude-plugin/                 plugin + marketplace manifests
├── .cursor/rules/
```

## Contributing

The rules that survive are the ones that change agent output. If you add a
pattern, include the mechanism, the fix, **and the conditions under which the
fix backfires** — the third one is what keeps this from becoming a list of
tricks.

## License

MIT
