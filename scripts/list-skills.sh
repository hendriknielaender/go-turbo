#!/usr/bin/env bash
# List every skill with its invocation mode.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '%-20s  %-14s  %s\n' SKILL INVOCATION DESCRIPTION
for skill in "$root"/skills/*/SKILL.md; do
  name=$(basename "$(dirname "$skill")")
  if grep -q '^disable-model-invocation: true' "$skill"; then
    mode=user-invoked
  else
    mode=model-invoked
  fi
  desc=$(sed -n 's/^description: //p' "$skill" | head -1)
  printf '%-20s  %-14s  %s\n' "$name" "$mode" "$desc"
done
