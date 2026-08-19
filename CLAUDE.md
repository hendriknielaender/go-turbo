Conventions for this repo. `AGENTS.md` is the *skill's* portable content for
agents working on Go; this file is how the repo itself is built.

Every `SKILL.md` is either model-invoked or user-invoked, and that choice decides
how its description is written and whether a `commands/` file would be
duplication. See [.agents/invocation.md](./.agents/invocation.md).

References under `skills/go-turbo/references/` are the disclosed tier: one branch
per file, small enough to read whole, routed from the primary `SKILL.md` and
listed in `README.md`. The single-source-of-truth table lives there too. See
[.agents/writing-references.md](./.agents/writing-references.md).

Every skill has a human-facing page at `docs/<skill-name>.md`, re-synced whenever
the skill is added, renamed, or changed. See
[.agents/writing-docs.md](./.agents/writing-docs.md).

`.agents/skills/` symlinks each skill for harnesses that read `~/.agents/skills`;
re-run `scripts/link-skills.sh` after adding or renaming one.
`scripts/list-skills.sh` prints the set with its invocation mode.

## Before committing

```sh
python3 scripts/validate.py && python3 scripts/check_snippets.py
```

Add a changeset for any user-visible change. `package.json` is the single version
authority; `scripts/sync-plugin-version.mjs` propagates it to both manifests.
