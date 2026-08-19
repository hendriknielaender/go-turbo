#!/usr/bin/env bash
# (Re)link every skill into .agents/skills/ so harnesses reading ~/.agents/skills
# pick up changes from a git pull. Re-run after adding or renaming a skill.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dest="$root/.agents/skills"

mkdir -p "$dest"
find "$dest" -maxdepth 1 -type l -delete
for skill in "$root"/skills/*/; do
  name=$(basename "$skill")
  ln -s "../../skills/$name" "$dest/$name"
  echo "linked $name"
done
