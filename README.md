<h1 align="center">go-turbo</h1>

<p align="center">
  <img alt="go-turbo logo" src="assets/go-turbo.png" height="150" /><br>
  <em>Evidence-driven Go performance engineering for coding agents.</em><br>
</p>

---

`go-turbo` teaches an agent to write ordinary idiomatic Go with strong
performance instincts, then become more specialized only when a workload and
measurement justify it. It covers implementation, design, review, diagnosis,
benchmarking, profiling, networking, and production scaling.

The central rule is leverage before cleverness: remove work, fix the algorithm,
control allocation and lifetime, amortize boundaries, bound concurrency, and
only then consider runtime or machine-specific tuning. Correctness, race
freedom, cancellation, deadlines, and ownership are never performance
tradeoffs.

## Codex

This repository is ready for Codex development and native plugin packaging:

- `.agents/skills/` exposes the primary skill and focused workflows through
  Codex's repository-local discovery path.
- `.codex-plugin/plugin.json` packages the complete promoted skill set for the
  native Codex plugin surface.
- `.agents/plugins/marketplace.json` exposes the repository as a local or
  Git-backed Codex marketplace.
- `skills/go-turbo/agents/openai.yaml` provides the display metadata, default
  prompt, and implicit-invocation policy.
- The core skill is self-contained and routes to references only when they are
  relevant to the current task.

Open this repository in Codex and ask for Go work normally, or invoke the skill
explicitly:

```text
$go-turbo implement this parser
$go-turbo review this handler for allocation and tail-latency risks
$go-turbo redline optimize this measured hot path
```

After the skill release has landed on the default branch, use this editable
install across Codex and other Agent-Skills-compatible harnesses:

```sh
npx skills@latest add hendriknielaender/go-turbo
```

The installer copies ordinary skill files into the selected harness. Updates
remain explicit through the installer rather than changing local files behind
your back.

After a GitHub release exists, the version-pinned native Codex plugin can be
installed from this repository marketplace:

```sh
codex plugin marketplace add hendriknielaender/go-turbo --ref v1.0.0
codex plugin add go-turbo@go-turbo
```

Restart the Codex desktop app after adding the marketplace or plugin. For local
development, opening this repository is sufficient because `.agents/skills/`
is discovered directly.

The public Plugins Directory is a separate OpenAI review and publication
process. A local manifest, Git tag, or GitHub Release does not imply that this
plugin has been approved or publicly listed.

## Claude Code and other agents

Claude Code can install the repository as a plugin:

```text
/plugin marketplace add hendriknielaender/go-turbo
/plugin install go-turbo
```

Every skill is its own slash command — `/go-turbo`, `/go-turbo-analyze`, and so
on. Agents that read repository instructions can use `AGENTS.md`; Cursor can use
`.cursor/rules/go-turbo.mdc`.

## Workflows

Skills split on one axis: who can reach them.

**Model-invoked** — the agent selects it, or you type it.

| Skill | Purpose |
| --- | --- |
| [`$go-turbo`](docs/go-turbo.md) | Implement, refactor, debug, design, or review performant idiomatic Go. |

**User-invoked** — reachable only by typing the name. The agent will never fire
these on its own, and no skill can call another, so triggers cannot overlap.

| Skill | Purpose |
| --- | --- |
| [`$go-turbo-analyze`](docs/go-turbo-analyze.md) | Diagnose a latency, CPU, memory, throughput, or scaling problem without editing code. |
| [`$go-turbo-improve`](docs/go-turbo-improve.md) | Apply a measured performance fix and verify behavior and effect. |
| [`$go-turbo-escape`](docs/go-turbo-escape.md) | Explain and reduce heap escapes that matter on the real path. |
| [`$go-turbo-bench`](docs/go-turbo-bench.md) | Create, run, and interpret representative Go benchmarks. |
| [`$go-turbo-review`](docs/go-turbo-review.md) | Review a diff for actionable performance regressions and premature complexity. |
| [`$go-turbo-audit`](docs/go-turbo-audit.md) | Produce a ranked whole-repository performance assessment. |
| [`$go-turbo-help`](docs/go-turbo-help.md) | Show the index of these workflows and the intensity levels. |

Each is its own slash command — `/go-turbo-analyze` and so on. `$go-turbo-help`
is the router when you are unsure which one fits.

## Performance ladder

1. Remove, defer, cache, coalesce, or short-circuit work.
2. Select the right algorithm, data structure, index, and ownership model.
3. Reduce material hot-path allocation and unintended retention.
4. Remove incidental heap escapes confirmed by compiler diagnostics.
5. Batch or buffer syscalls, queries, RPCs, encodes, locks, and handoffs.
6. Bound concurrency and address measured contention and backpressure.
7. Only then tune layout, pooling, protocols, the runtime, or hardware.

Straightforward changes still have preconditions. Capacity should come from an
exact or defensible bound; buffering needs flush and error semantics; field
layout can be externally visible; zero-copy introduces ownership and aliasing
rules. The skill states those conditions rather than handing out context-free
tricks.

Complex changes need representative evidence. Pooling, lock sharding,
cache-line padding, mmap, raw socket controls, runtime knobs, PGO, `unsafe`,
assembly, and SIMD ship only with a measured benefit, a tradeoff contract, and
a removal trigger.

## Knowledge base

| Reference | Covers |
| --- | --- |
| **Measure** | |
| `writing-benchmarks.md` | Writing one you can trust. |
| `comparing-benchmarks.md` | Benchstat, repeats, variance. |
| `pprof.md` | CPU and memory profiles. |
| `block-profiles.md` | Blocking, mutex, traces. |
| `load-testing.md` | Open-loop, coordinated omission. |
| `workflow.md` | Baseline improvements, intensity levels. |
| **Allocate** | |
| `finding-allocations.md` | Locating the site. |
| `presizing.md` | Capacity from a bound. |
| `interface-boxing.md` | Conversion vs allocation. |
| `pooling.md` | Sync. |
| `retention.md` | Sub-slice holding a big array. |
| `strings-and-bytes.md` | String/[]byte round trips, building. |
| `memory-layout.md` | Padding, false sharing, aliasing. |
| **Escapes** | |
| `escape-analysis.md` | Reading -gcflags=-m. |
| `escape-causes.md` | The shapes that escape. |
| `necessary-escapes.md` | When to leave it. |
| `caller-owned-buffers.md` | AppendX, reusable storage. |
| `value-semantics.md` | Values, stack scratch. |
| `hot-dispatch.md` | Concrete types, inlining coupling. |
| **Choose a structure** | |
| `choosing-structures.md` | From the workload. |
| `map-vs-slice.md` | The crossover. |
| `pointer-density.md` | GC cost of layout. |
| `sorting.md` | Sort once, query many. |
| `heaps.md` | Priority queues. |
| `monotonic-stacks.md` | Nested scans in one pass. |
| `in-place-transforms.md` | Filter and compact in place. |
| `queues-and-rings.md` | Bounded queues, rings. |
| **Run** | |
| `gc-cost.md` | What the collector spends. |
| `gc-tuning.md` | GOGC, GOMEMLIMIT. |
| `gc-diagnosis.md` | Gctrace, heap, metrics. |
| `object-lifetime.md` | Weak pointers, cleanups. |
| `gomaxprocs.md` | CPU quota. |
| `scheduler-state.md` | G-M-P pressure. |
| `goroutine-budgets.md` | Budget by retained state. |
| `netpoll.md` | The event loop you already have. |
| **Compile** | |
| `compiler-diagnostics.md` | Build context, reading decisions. |
| `inlining.md` | Cost model, devirtualization. |
| `bounds-check-elimination.md` | BCE. |
| `pgo.md` | Profile-guided optimization. |
| `build-flags.md` | Release and target flags. |
| `cgo.md` | Call cost, static linking. |
| `build-experiments.md` | GOEXPERIMENT, assembly, SIMD. |
| **Upgrade the toolchain** | |
| `upgrade-experiment.md` | The contract. |
| `benchmark-inputs.md` | Deterministic, warm and cold. |
| `same-host-comparison.md` | One machine, interleaved. |
| `sample-variance.md` | How many samples. |
| `run-metadata.md` | What makes it reproducible. |
| `interpreting-results.md` | Canary and rollback. |
| **Coordinate** | |
| `bounding-concurrency.md` | Fan-out, choosing the bound. |
| `backpressure.md` | Signalling the producer. |
| `mutexes-and-atomics.md` | Cheapest coordination. |
| `sharding.md` | Splitting a contended lock. |
| `immutable-snapshots.md` | Publish, lazy init. |
| `channels.md` | Value ownership. |
| `context-cancellation.md` | Propagating cancellation. |
| `graceful-shutdown.md` | Signals, drain order. |
| `goroutine-leaks.md` | Lifetime and exit paths. |
| **Cross a boundary** | |
| `buffering.md` | Repeated small I/O. |
| `batching.md` | Grouping without holding locks. |
| `stream-copies.md` | Io. |
| `framing.md` | Bounded length prefixes. |
| `files-and-mmap.md` | File APIs, memory mapping. |
| **Encode** | |
| `json.md` | Typed and streaming. |
| `binary-encoding.md` | Wire formats, append-oriented. |
| `base64.md` | Exact output sizing. |
| `text-processing.md` | Number formatting, regexps. |
| `hashing.md` | Checksums, streaming hashers. |
| `aead-nonces.md` | Nonce reuse is a security bug. |
| `compression.md` | Codec choice, reuse, bounds. |
| **Talk to the network** | |
| `http-connection-reuse.md` | The usual cause. |
| `http-client-config.md` | Transport sharing. |
| `httptrace.md` | Was it reused. |
| `request-deadlines.md` | Timeouts, retry budgets. |
| `http-servers.md` | Server timeouts, release. |
| `http2-tuning.md` | Streams, flow control. |
| `tls.md` | Handshake, resumption. |
| `dns.md` | Resolution, caching. |
| `protocol-selection.md` | Which protocol. |
| `http-versions.md` | 1. |
| `grpc.md` | Unary and streaming. |
| `tcp-framing.md` | Raw TCP. |
| `udp.md` | Datagrams. |
| `quic.md` | Streams, migration. |
| `socket-options.md` | Kernel buffers, setsockopt. |
| `connection-scale.md` | 10k+ connections, accept loops. |
| **Survive load** | |
| `resource-budgets.md` | What the process has. |
| `admission-control.md` | What to accept. |
| `rate-limiting.md` | Limiter algorithms. |
| `bounded-queues.md` | Sizing and full policy. |
| `load-shedding.md` | Shedding, 503s. |
| `circuit-breakers.md` | Stop paying for failure. |
| `retries.md` | Idempotency, budgets, jitter. |

The Go examples are syntax-checked with the Go toolchain used by validation;
that does not type-check every API or prove runtime behavior. Version-specific
claims name their minimum where relevant and must be revalidated with the exact
toolchain and deployment target in use.

## Repository layout

```text
go-turbo/
├── .agents/
│   ├── plugins/marketplace.json      Codex repository marketplace
│   └── skills/                       Codex repository-local entries
├── .changeset/                       semantic-version proposals
├── .codex-plugin/plugin.json         native Codex plugin manifest
├── .claude-plugin/                   Claude plugin manifests
├── .github/workflows/                validation and release automation
├── AGENTS.md                         portable minimum rules
├── CLAUDE.md                         repo conventions for agents editing it
├── docs/                             one human-facing page per skill
├── .agents/                          invocation, reference and docs doctrine
├── assets/                           Codex plugin brand assets
├── CHANGELOG.md                      released user-visible changes
├── package.json                      single version authority
├── skills/
│   ├── go-turbo/
│   │   ├── SKILL.md                  primary workflow
│   │   ├── agents/openai.yaml        Codex metadata and policy
│   │   └── references/               focused knowledge base
│   └── go-turbo-*/                   optional explicit workflows
├── .cursor/rules/                    Cursor adapter
├── tests/                             behavior and submission contracts
└── scripts/                           validation and version synchronization
```

## Release contract

`package.json` is the version authority. `npm run version` applies a Changesets
version plan and synchronizes both plugin manifests. `npm run validate` checks
the skill inventory, Codex metadata, release metadata, prohibited provenance,
Go snippets, and manifest-version parity.

The two Python programs under `scripts/` are dependency-free, read-only content
gates for Markdown skill structure and embedded Go examples. They run in the
validation job, not in the release job. A successful validation job for an
exact `main` commit calls the Node-only release workflow in that same GitHub
Actions run. Changesets creates or updates the version pull request; once that
pull request is merged, a fail-closed finalizer creates the matching tag and
GitHub Release and attaches a skills-only ZIP plus SHA-256 checksum built from
the reviewed Git commit.

```sh
npm ci --ignore-scripts
npm run changeset
npm run validate
```

A version in `package.json` or a plugin manifest is a release candidate until a
matching `vX.Y.Z` tag and GitHub Release exist. See
[the release decision](.agents/adr/0001-release-and-distribution.md) for the
full inventory and publication invariants.

## Contributing

New guidance must say what cost it addresses, when it is applicable, how to
measure it, and when it backfires. Prefer primary Go documentation and original
examples. Keep toolchain-dependent statements versioned and testable. Run the
fresh-agent cases in `tests/behavioral-cases.md` after changing skill behavior.

## License

MIT
