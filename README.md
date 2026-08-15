<h1 align="center">go-turbo</h1>

<p align="center">
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

The `commands/` directory supplies Claude slash-command adapters. Agents that
read repository instructions can use `AGENTS.md`; Cursor can use
`.cursor/rules/go-turbo.mdc`.

## Workflows

| Skill | Purpose |
| --- | --- |
| `$go-turbo` | Implement, refactor, debug, design, or review performant idiomatic Go. |
| `$go-turbo-analyze` | Diagnose a latency, CPU, memory, throughput, or scaling problem without editing code. |
| `$go-turbo-improve` | Apply a measured performance fix and verify behavior and effect. |
| `$go-turbo-escape` | Explain and reduce heap escapes that matter on the real path. |
| `$go-turbo-bench` | Create, run, and interpret representative Go benchmarks. |
| `$go-turbo-review` | Review a diff for actionable performance regressions and premature complexity. |
| `$go-turbo-audit` | Produce a ranked whole-repository performance assessment. |
| `$go-turbo-help` | Show the workflow and evidence reference card. |

The focused skills are optional, explicit workflows. Their Codex metadata
disables implicit invocation, so only the primary skill can be selected
automatically and the triggers do not overlap.

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
| `data-structures.md` | Cost models, small collections, maps, sorting, heaps, rings, queues, indexes, and memory-oriented layouts. |
| `allocation.md` | Slices, maps, builders, boxing, pools, layout, aliasing, string/byte conversions, and retention. |
| `escape-analysis.md` | Compiler diagnostics, lifetime causes, stack-friendly API shapes, closures, interfaces, and inlining nuance. |
| `gc-and-runtime.md` | GC pacing and limits, managed memory, stacks, scheduler behavior, netpoll, and runtime observability. |
| `concurrency.md` | Bounded work, synchronization choices, sharding, immutable publication, cancellation, leaks, and backpressure. |
| `io-and-syscalls.md` | Buffering, batching, copies, framing, file access, mmap, databases, RPCs, flush, and error contracts. |
| `encoding-and-text.md` | Binary and JSON encoding, formatting, regexps, parsing, hashing, crypto, and compression choices. |
| `networking.md` | HTTP clients and servers, connection reuse, TLS, DNS, socket controls, long-lived connections, and observability. |
| `protocols.md` | TCP, UDP, HTTP/1.1, HTTP/2, HTTP/3, gRPC, QUIC, multiplexing, flow control, and replay-safe early data. |
| `scaling-and-resilience.md` | Admission control, overload, circuit breaking, shedding, retries, degradation, graceful shutdown, and high connection counts. |
| `measurement.md` | Benchmark construction, benchstat, profiles, traces, load tests, variance, and claim boundaries. |
| `compiler.md` | Diagnostics, inlining, devirtualization, bounds checks, PGO, flags, cgo, experiments, and disassembly. |
| `toolchain-upgrades.md` | Release-to-release benchmarking, compatibility, rollout, regression isolation, and rollback evidence. |

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
├── assets/                           Codex plugin brand assets
├── CHANGELOG.md                      released user-visible changes
├── commands/                         Claude command adapters
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
