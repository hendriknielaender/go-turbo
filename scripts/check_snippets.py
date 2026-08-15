#!/usr/bin/env python3
"""Syntax-check every Go snippet in the go-turbo docs.

Snippets in a knowledge base get read as authoritative, so one that doesn't
parse is a real defect. Most are fragments rather than whole files, so each
block is wrapped in the smallest enclosing scope that makes it parseable and
handed to `gofmt -e`, which reports syntax errors without needing imports to
resolve.

Several wrapping strategies are tried in order, because a fragment may be a
whole file, a set of top-level declarations, a run of statements, or a mix of
declarations and statements. A block is a failure only if none of them parse.

Blocks that are deliberately incomplete must be preceded by an HTML comment
containing `check-snippets: skip`. Valid Go uses `...` in variadic syntax, so
ellipsis text is not an automatic exemption.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = [
    *sorted((ROOT / "skills").rglob("*.md")),
    ROOT / "README.md",
    ROOT / "AGENTS.md",
]

BLOCK = re.compile(r"```go\n(.*?)```", re.DOTALL)
SKIP_MARK = "check-snippets: skip"
DECL_PREFIX = ("import ", "import(", "type ", "const ", "var ", "func ", "//go:")

failures: list[str] = []
checked = 0
skipped = 0


def split_decls(src: str) -> tuple[str, str]:
    """Separate top-level declarations from loose statements.

    Declarations start at column 0 with a declaration keyword and run until
    their brackets balance. Everything else is treated as statement-level.
    """
    lines = src.split("\n")
    decls: list[str] = []
    stmts: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        starts_decl = (
            line[:1] not in (" ", "\t")
            and line.strip().startswith(DECL_PREFIX)
        )
        if not starts_decl:
            stmts.append(line)
            i += 1
            continue

        depth = 0
        while i < len(lines):
            l = lines[i]
            depth += l.count("{") + l.count("(") + l.count("[")
            depth -= l.count("}") + l.count(")") + l.count("]")
            decls.append(l)
            i += 1
            if depth <= 0:
                break

    return "\n".join(decls), "\n".join(stmts)


def candidates(src: str) -> list[str]:
    """Wrapping strategies to try, cheapest first."""
    out = [src]                                        # already a whole file
    out.append("package p\n\n" + src)                  # top-level declarations
    out.append("package p\n\nfunc _() {\n" + src + "\n}\n")  # statements

    decls, stmts = split_decls(src)
    if decls.strip() and stmts.strip():                # a mix of both
        out.append(
            "package p\n\n" + decls + "\n\nfunc _() {\n" + stmts + "\n}\n"
        )
    return out


def gofmt(src: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".go", delete=False) as f:
        f.write(src)
        path = f.name
    try:
        proc = subprocess.run(["gofmt", "-e", path], capture_output=True, text=True)
        return proc.returncode == 0, proc.stderr.strip()
    finally:
        pathlib.Path(path).unlink(missing_ok=True)


def main() -> int:
    global checked, skipped

    for doc in DOCS:
        if not doc.exists():
            continue
        text = doc.read_text(encoding="utf-8")
        rel = doc.relative_to(ROOT)

        for match in BLOCK.finditer(text):
            body = match.group(1)
            preceding = text[max(0, match.start() - 200):match.start()]

            if SKIP_MARK in preceding:
                skipped += 1
                continue
            checked += 1
            last_err = "parse error"
            for candidate in candidates(body):
                ok, err = gofmt(candidate)
                if ok:
                    break
                if err:
                    last_err = err.splitlines()[0]
            else:
                line = text[:match.start()].count("\n") + 1
                msg = re.sub(r"^\S*\.go:", "", last_err).strip()
                failures.append(f"{rel}:{line}: {msg}")

    if failures:
        print(f"FAIL: {len(failures)} snippet(s) do not parse\n", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    print(f"OK: {checked} Go snippets parse ({skipped} skipped as fragments)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
