# Writing references

`skills/go-turbo/references/` is the disclosed tier: material reached through a
pointer in `skills/go-turbo/SKILL.md`, loaded only when that pointer fires.

## One branch, read whole

A reference covers exactly one branch — one question a task arrives with — and
is small enough to read entirely. The current set runs roughly 290–1250 words.

Size is the symptom, not the rule. When a file grows past the range the cause is
almost always two branches sharing a filename: hashing next to regexps, TLS next
to HTTP client configuration, rate limiting next to admission control. Split on
the branch. A file that is genuinely one question and happens to be long is
fine; a short file covering two is not.

The test: would a task that needs section A also need section B? If most tasks
need only one, they are different branches.

## Rules

- Every reference is routed from `skills/go-turbo/SKILL.md` as
  `references/<name>` and listed in `README.md`. `scripts/validate.py` enforces
  both.
- A `## Contents` index earns its place only where there is something to
  navigate: over 100 lines *and* three or more sections. Below either bar it is
  furniture, and a one-entry index is the title restated.
- `COVERAGE` in `scripts/validate.py` is a map of capability phrases the
  knowledge base promises. Moving a section means relocating its phrase, never
  dropping it.
- A reference that names a sibling does it in backticks (`rate-limiting.md`), so
  the pointer survives the file moving.

## Single source of truth

Each of these lives in exactly one place. Point at it; restating one is how they
drift.

| Material | Home |
| --- | --- |
| The performance ladder | `skills/go-turbo/SKILL.md` |
| The `turbo:` comment format | `skills/go-turbo/SKILL.md` |
| Intensity levels | `references/workflow.md` |
| Before/after benchmark procedure | `references/benchmarking.md` |
