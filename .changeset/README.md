# Changesets

Every user-visible skill or packaging change needs a changeset. Run
`npm run changeset`, select `go-turbo`, choose the smallest accurate semantic
version bump, and describe the user-visible effect.

Merging the generated version pull request updates `package.json`, the lockfile,
both plugin manifests, and `CHANGELOG.md`; the next release run creates the
matching Git tag and GitHub Release. This private package is version authority
only and is never published to npm.
