#!/usr/bin/env python3
"""Run execution for the go-turbo eval suite.

One run is a single (task, model, arm, repeat) combination executed in its own
copy of the task fixture. Runs are independent, resumable, and never share a
working directory.

Fairness rules, enforced here rather than left to the caller:

  * Every arm gets byte-identical prompts. An arm may only add process-level
    flags (a plugin directory, a system prompt), never task text.
  * Every arm runs with `--setting-sources project` from a directory with no
    project settings, so the operator's own global skills, CLAUDE.md, and
    plugins cannot leak into any arm.
  * The fixture is re-copied per repeat, so one run cannot see another's edits.
  * The model spec is passed straight through, so any model the CLI accepts is
    a valid arm member.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import time
import uuid
from typing import Any


class ModelSpec:
    """A model and optional effort level, written `model` or `model:effort`."""

    EFFORTS = {"low", "medium", "high", "xhigh", "max"}

    def __init__(self, raw: str):
        self.raw = raw
        if ":" in raw:
            model, effort = raw.split(":", 1)
            if effort not in self.EFFORTS:
                raise ValueError(
                    f"unknown effort {effort!r} in {raw!r}; use one of {sorted(self.EFFORTS)}"
                )
            self.model = model
            self.effort = effort
        else:
            self.model = raw
            self.effort = None

    @property
    def slug(self) -> str:
        return self.raw.replace(":", "-").replace(".", "_")

    def cli_args(self) -> list[str]:
        args = ["--model", self.model]
        if self.effort:
            args += ["--effort", self.effort]
        return args

    def __repr__(self) -> str:
        return f"ModelSpec({self.raw!r})"


class Arm:
    """A condition under test: a name plus the process flags that define it."""

    def __init__(self, name: str, spec: dict[str, Any], repo_root: pathlib.Path):
        self.name = name
        self.description = spec.get("description", "")
        self.extra_args: list[str] = []

        for plugin in spec.get("plugin_dirs", []):
            path = (repo_root / plugin).resolve() if not plugin.startswith("/") else pathlib.Path(plugin)
            self.extra_args += ["--plugin-dir", str(path)]

        if spec.get("append_system_prompt_file"):
            path = repo_root / spec["append_system_prompt_file"]
            self.extra_args += ["--append-system-prompt", path.read_text()]

        if spec.get("append_system_prompt"):
            self.extra_args += ["--append-system-prompt", spec["append_system_prompt"]]

        self.extra_args += list(spec.get("extra_args", []))


class Run:
    def __init__(self, task: str, model: ModelSpec, arm: Arm, repeat: int):
        self.task = task
        self.model = model
        self.arm = arm
        self.repeat = repeat

    @property
    def run_id(self) -> str:
        return f"{self.task}__{self.model.slug}__{self.arm.name}__r{self.repeat}"


def execute(
    run: Run,
    task_dir: pathlib.Path,
    work_root: pathlib.Path,
    timeout: int,
) -> dict[str, Any]:
    """Execute one run and return its record. Never raises on agent failure."""
    work_dir = work_root / run.run_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(task_dir / "fixture", work_dir)

    prompt = (task_dir / "prompt.md").read_text()
    transcript_path = work_root / f"{run.run_id}.jsonl"

    cmd = [
        "claude", "-p",
        *run.model.cli_args(),
        "--setting-sources", "project",
        "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
        "--output-format", "stream-json", "--verbose",
        "--session-id", str(uuid.uuid4()),
        *run.arm.extra_args,
        prompt,
    ]

    started = time.time()
    timed_out = False
    try:
        with transcript_path.open("w") as out:
            proc = subprocess.run(
                cmd, cwd=work_dir, stdout=out, stderr=subprocess.PIPE,
                text=True, timeout=timeout,
            )
        stderr = proc.stderr[-4000:]
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        stderr = f"run exceeded {timeout}s"
        exit_code = -1
    elapsed = time.time() - started

    record = {
        "run_id": run.run_id,
        "task": run.task,
        "model": run.model.raw,
        "arm": run.arm.name,
        "repeat": run.repeat,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "wall_seconds": round(elapsed, 1),
        "work_dir": str(work_dir),
        "transcript": str(transcript_path),
        "stderr": stderr,
    }
    record.update(parse_transcript(transcript_path))
    return record


def parse_transcript(path: pathlib.Path) -> dict[str, Any]:
    """Extract usage and process metrics from a stream-json transcript.

    Process metrics matter as much as the score. The Agentic Benchmark
    Checklist asks for process-based signals alongside outcome-based ones, and
    for a skill eval the tool trace is the only way to see whether the skill
    was loaded at all, and which of its references were actually read.
    """
    events: list[dict[str, Any]] = []
    if path.exists():
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    result = next((e for e in events if e.get("type") == "result"), None)
    tools: dict[str, int] = {}
    skills_invoked: list[str] = []
    files_read: list[str] = []
    thinking_chars = 0

    for e in events:
        if e.get("type") != "assistant":
            continue
        for blk in e.get("message", {}).get("content", []) or []:
            kind = blk.get("type")
            if kind == "thinking":
                thinking_chars += len(blk.get("thinking", ""))
            elif kind == "tool_use":
                name = blk.get("name", "?")
                tools[name] = tools.get(name, 0) + 1
                inp = blk.get("input") or {}
                if name == "Skill":
                    skills_invoked.append(str(inp.get("skill", "?")))
                elif name == "Read":
                    files_read.append(str(inp.get("file_path", "")))

    usage = (result or {}).get("usage", {}) or {}
    inp = usage.get("input_tokens", 0)
    cw = usage.get("cache_creation_input_tokens", 0)
    cr = usage.get("cache_read_input_tokens", 0)
    out = usage.get("output_tokens", 0)

    return {
        "success": (result or {}).get("subtype") == "success",
        "answer": (result or {}).get("result", ""),
        "turns": (result or {}).get("num_turns", 0),
        "cost_usd": round((result or {}).get("total_cost_usd") or 0.0, 6),
        "input_tokens": inp,
        "cache_write_tokens": cw,
        "cache_read_tokens": cr,
        "output_tokens": out,
        "total_tokens": inp + cw + cr + out,
        "tool_calls": sum(tools.values()),
        "tools": tools,
        "skills_invoked": skills_invoked,
        "skill_files_read": [p for p in files_read if "skills/" in p and p.endswith(".md")],
        "thinking_chars": thinking_chars,
    }
