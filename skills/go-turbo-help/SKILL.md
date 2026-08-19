---
name: go-turbo-help
description: Which go-turbo workflow to reach for, and the intensity levels.
disable-model-invocation: true
---

# Go Turbo Help

Display this card. Inspect no code and change no files.

## The map

`$go-turbo` is the core, and the only one the model can reach on its own. The
rest are focused cuts of it that fire only when you type them; each one's own
description is already in your slash-command list, so route here, don't restate
it.

The usual path through a performance problem:

```
$go-turbo-analyze  →  $go-turbo-improve
  (what is slow)       (fix it, prove it)
         ↑
  $go-turbo-bench — the evidence either step runs on
```

Enter elsewhere when the shape differs: `$go-turbo-review` for a diff,
`$go-turbo-audit` for a whole repo, `$go-turbo-escape` when the question is
specifically heap escapes.

## Intensity

`$go-turbo` runs at `turbo` unless you name a level — `cruise` for safe baseline
improvements only, `redline` to chase every measured hot-path cost under the same
correctness and evidence gates. Defined in
`skills/go-turbo/references/workflow.md`.

## The rules behind all of them

The performance ladder, the evidence gate, and the reference map live in
`skills/go-turbo/SKILL.md`. Read it there rather than from a summary — the ladder
is what decides what these skills do.
