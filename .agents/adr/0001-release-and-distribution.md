# ADR 0001: Release and distribution authority

## Decision

`package.json` is the single semantic-version authority. The Claude and Codex
plugin manifests must carry that exact version, and the synchronization check
is a required validation gate.

Every directory directly below `skills/` is promoted. The same eight-skill
inventory must appear in the Claude manifest, Codex repository discovery,
README workflow table, and command adapters. The native Codex manifest points
at the single promoted root, `./skills/`.

Changesets owns version proposals and changelog generation, but it does not own
tag or release creation. A push to `main` must pass the complete read-only
validation job before that same workflow run may call the Node-only release job
for the exact validated commit. Only then may the release workflow update its
version pull request or create a tag. A release exists only when `vX.Y.Z`, the
GitHub Release, both plugin manifests, `package.json`, and the attached ZIP all
name the same version.

The release finalizer runs only when the committed version is nonzero, differs
from its first parent, and no changeset remains. It creates or verifies the tag
at that exact validated commit and fails closed on any mismatch. This makes a
rerun recover a partial release without allowing a later same-version commit to
claim an absent tag.

The submitted ZIP is built with `git archive` from an allowlist in the reviewed
commit. It contains the native Codex manifest, the real `skills/` tree, the
brand assets, the license, privacy and terms, and release-facing documentation.
The workflow rejects symlinks in that set before packaging and publishes a
SHA-256 checksum beside the ZIP. Repository discovery links, development
adapters, dependency trees, and local configuration are never submitted.

## Distribution surfaces

- Codex repository discovery uses `.agents/skills/` during development.
- The native Codex plugin and repository marketplace provide installable local
  and Git-backed distribution.
- The skills installer copies editable skill files for Codex and other
  Agent-Skills-compatible harnesses.
- The Claude manifest and command adapters remain a compatibility surface.
- Public plugin directories are external publication surfaces. A local tag or
  manifest must never be described as approved or publicly listed.

Shared skill frontmatter stays within the Codex skill schema. Harness-specific
invocation policy belongs in harness metadata or adapters; Claude-only
frontmatter must not make the common skill fail Codex validation.

## Release process

1. Add a changeset for every user-visible skill or packaging change.
2. Merge normal changes only after `npm run validate` passes.
3. Merge the generated version pull request after reviewing the version,
   changelog, and synchronized manifests.
4. Successful validation of the exact `main` commit calls the release workflow,
   which verifies version parity, creates the matching tag and GitHub Release,
   and attaches the deterministic skills-only ZIP and checksum.
5. Submit that exact ZIP to external directories. Record external approval and
   publication separately; they cannot be proven by repository CI.
