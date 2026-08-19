# Model-invoked vs user-invoked

Every `SKILL.md` here is a skill. The one axis that splits them is **invocation**
— who can reach it.

- **Model-invoked** — reachable by model or user. `go-turbo` is the only one.
  Omit `disable-model-invocation`, and set `policy.allow_implicit_invocation:
  true` in `agents/openai.yaml`. Its `description` is **model-facing** and keeps
  rich trigger phrasing, because that description is what fires it.
- **User-invoked** — reachable only by the human typing its name. Set
  `disable-model-invocation: true` (Claude) and
  `policy.allow_implicit_invocation: false` (Codex). The `description` is
  **human-facing**: a one-line summary read by a person browsing slash commands.
  Strip trigger phrasing.

Keep the two harnesses in sync: a skill is user-invoked in both or neither.

The test for whether a skill should stay model-invoked is whether the model
could usefully reach for it autonomously. Reuse is a reason to extract a skill,
not a reason to make it model-invocable.

## Why user-invoked descriptions are short

Nothing but the human can fire a user-invoked skill, so "Use when the user
says…" is text that pays context on every turn and can never act on anything.
One trigger per branch; synonyms that rename a single branch are one branch
written twice.

## No commands directory

A skill is already a slash command. A command file that only delegates to it
(`Run the X skill on: $ARGUMENTS`) puts the same pointer in context twice — once
as a skill description, once as a command description. `argument-hint` belongs
in the skill's own frontmatter.

## Dependencies between skills

No skill can call a user-invoked skill; that is the invariant the flag creates.
Where a companion needs shared material it points at a file under
`skills/go-turbo/references/`, never at another companion.

This diverges from the convention of naming the Skill tool instead of linking
across folders, and the divergence is deliberate: the owning skill here is
`go-turbo`, and routing through it would load the whole primary skill to reach
one reference section. The reference link costs nothing until it is read.

## Invocation syntax

Skills are named `$go-turbo` in prose, not `/go-turbo`. Codex uses the `$` form
and `scripts/validate.py` enforces it.
