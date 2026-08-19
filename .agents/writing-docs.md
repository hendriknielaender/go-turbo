# Writing docs pages

Every skill has a human-facing page at `docs/<skill-name>.md`. It is not the
skill and not a copy of `SKILL.md`.

Most of these skills are user-invoked: the agent will never fire them, so a
human has to remember they exist and when to reach for each. That memory is
cognitive load, and relieving it is the page's whole job.

Re-sync a page whenever a skill is added, renamed, or changes behaviour. A
rename moves the file too.

## Structure

1. `## What it does` — one or two plain paragraphs. Lead with the one-sentence
   job, then the **defining constraint**: the single fact that makes this skill
   behave differently from the obvious default. Write it as plain prose, never
   as a labelled aside.
2. `## When to reach for it` — state the invocation mode ("Type `/x` — the agent
   will not fire it on its own") and the trigger boundary. Where the skill is
   confusable with a sibling, give the other half.
3. The middle — one to three sections in the skill's own vocabulary that make it
   click. No prescribed heading.
4. `## Common questions` — bold question, answer beneath, no sub-headings.
5. `## It's working if` — bullets naming what the reader sees when it works.
6. `## Where it fits` — role and neighbours, in a sentence or two.

## Conventions

- Explain the why, not the process. The page never reproduces `SKILL.md`'s steps.
- Every multi-way branch is a table or a list, never a paragraph the reader has
  to read in full to find their row.
- Name no author and quote no author. Every claim stands on its own.
- Carry no install commands.
- Every `## It's working if` bullet must be checkable without opening
  `SKILL.md` — a signal in the reader's own work, not a compliance check on the
  skill's internals.
- **Size `## Common questions` to evidence, never to symmetry.** `evals/` and
  `tests/behavioral-cases.md` are the sources. A page with two real questions is
  finished; padding it to match a richer page fills the section with questions
  nobody asked, and an invented question teaches nobody. Say the unflattering
  thing where it is true.
