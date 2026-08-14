#!/usr/bin/env python3
"""Structural validation for the go-turbo plugin.

Checks that skills, commands, and manifests are internally consistent and that
no upstream source attribution leaked into the published text.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Text that must never appear in shipped files.
FORBIDDEN = [
    "goperf.dev",
    "go-optimization-guide",
    "astavonin",
]

errors: list[str] = []
checked = 0


def fail(msg: str) -> None:
    errors.append(msg)


def split_frontmatter(text: str, path: pathlib.Path) -> dict | None:
    if not text.startswith("---\n"):
        fail(f"{path}: missing YAML frontmatter")
        return None
    end = text.find("\n---\n", 3)
    if end == -1:
        fail(f"{path}: unterminated YAML frontmatter")
        return None
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        fail(f"{path}: invalid YAML frontmatter: {exc}")
        return None
    if not isinstance(data, dict):
        fail(f"{path}: frontmatter is not a mapping")
        return None
    return data


def check_skills() -> set[str]:
    names: set[str] = set()
    skill_files = sorted((ROOT / "skills").glob("*/SKILL.md"))
    if not skill_files:
        fail("no skills found under skills/")
        return names

    for path in skill_files:
        global checked
        checked += 1
        text = path.read_text(encoding="utf-8")
        fm = split_frontmatter(text, path)
        if fm is None:
            continue

        name = fm.get("name")
        desc = fm.get("description")

        if not name:
            fail(f"{path}: frontmatter missing 'name'")
        elif name != path.parent.name:
            fail(f"{path}: name '{name}' != directory '{path.parent.name}'")
        else:
            names.add(name)

        if not desc:
            fail(f"{path}: frontmatter missing 'description'")
        elif len(desc) < 80:
            fail(f"{path}: description too short to trigger reliably "
                 f"({len(desc)} chars)")

        body_lines = text.count("\n")
        if body_lines > 500:
            fail(f"{path}: {body_lines} lines, over the 500-line guideline")

    return names


def check_references() -> None:
    global checked
    refs = sorted((ROOT / "skills" / "go-turbo" / "references").glob("*.md"))
    if not refs:
        fail("no reference files found")
        return

    skill = (ROOT / "skills" / "go-turbo" / "SKILL.md").read_text(encoding="utf-8")
    for path in refs:
        checked += 1
        rel = f"references/{path.name}"
        if rel not in skill:
            fail(f"{rel} is not referenced from skills/go-turbo/SKILL.md")


def check_commands(skill_names: set[str]) -> None:
    global checked
    cmds = sorted((ROOT / "commands").glob("*.md"))
    if not cmds:
        fail("no commands found under commands/")
        return

    for path in cmds:
        checked += 1
        text = path.read_text(encoding="utf-8")
        fm = split_frontmatter(text, path)
        if fm is None:
            continue
        if not fm.get("description"):
            fail(f"{path}: frontmatter missing 'description'")
        if path.stem not in skill_names:
            fail(f"{path}: no skill named '{path.stem}'")


def check_manifests() -> None:
    global checked
    for rel in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
        path = ROOT / rel
        checked += 1
        if not path.exists():
            fail(f"{rel}: missing")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"{rel}: invalid JSON: {exc}")
            continue
        if data.get("name") != "go-turbo":
            fail(f"{rel}: name is not 'go-turbo'")


def check_forbidden() -> None:
    global checked
    tracked = [
        p for p in ROOT.rglob("*")
        if p.is_file()
        and ".git/" not in str(p)
        and p.suffix in {".md", ".mdc", ".json", ".yml", ".yaml", ".py"}
    ]
    pattern = re.compile("|".join(re.escape(t) for t in FORBIDDEN), re.IGNORECASE)
    for path in tracked:
        checked += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            # The FORBIDDEN list itself lives in this file.
            if path.name == "validate.py":
                continue
            m = pattern.search(line)
            if m:
                rel = path.relative_to(ROOT)
                fail(f"{rel}:{lineno}: forbidden reference '{m.group(0)}'")


def main() -> int:
    skill_names = check_skills()
    check_references()
    check_commands(skill_names)
    check_manifests()
    check_forbidden()

    if errors:
        print(f"FAIL: {len(errors)} problem(s)\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(f"OK: {checked} checks passed, {len(skill_names)} skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
