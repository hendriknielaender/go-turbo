#!/usr/bin/env python3
"""Grading for the go-turbo eval suite.

Two grader kinds:

`script`  An executable in the task directory scores the produced tree and
          prints one JSON object. Deterministic and model-free, so it is the
          preferred kind wherever the task has a checkable outcome.

`judge`   A pinned model scores the final answer against a fixed rubric. Used
          only for tasks whose product is a judgement rather than an artifact.

Outcome validity (Agentic Benchmark Checklist, arXiv:2507.02825) is enforced
mechanically: before any script grader runs, every file in the task's
`holdout/` directory is copied over the agent's tree. An agent that weakened,
deleted, or rewrote the contract tests is graded against the originals anyway.

Judge bias controls:
  * Pointwise, never pairwise. The judge sees one answer at a time and never
    learns which arm or model produced it, so there is no position to be
    biased by and no arm identity to prefer.
  * The judge model is pinned in suite.json and recorded in every result.
  * The judge is sampled `judge_repeats` times and averaged, since a single
    judge draw is itself a noisy measurement.
  * Rubric items are enumerated and scored individually rather than holistically,
    which limits the verbosity preference that afflicts holistic scoring.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import pathlib
import re
import shutil
import random
import subprocess
import tempfile
import threading
import time
from typing import Any

# Judge calls are long (tens of seconds, thousands of output tokens). Too many
# at once start failing, and the failures are silent. This bounds the total
# across all grading threads, independent of --jobs.
MAX_CONCURRENT_JUDGE_CALLS = 2
_judge_slots = threading.Semaphore(MAX_CONCURRENT_JUDGE_CALLS)


class GradeResult:
    """A grade, or an explicit grading failure.

    `error=True` means the grader could not produce a verdict — a judge that
    never returned parsable JSON, a crashed script. That is NOT a score of
    zero. Recording a grading failure as 0.0 makes a broken harness look
    exactly like a terrible answer, which silently corrupts every comparison
    downstream. Callers must skip errored grades so they can be retried.
    """

    def __init__(self, score: float, passed: bool, metrics: dict[str, Any],
                 detail: str = "", error: bool = False):
        self.score = max(0.0, min(1.0, float(score)))
        self.passed = bool(passed)
        self.metrics = metrics
        self.detail = detail
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "metrics": self.metrics,
            "detail": self.detail,
            "error": self.error,
        }


def _stage_for_grading(run_dir: pathlib.Path, task_dir: pathlib.Path) -> pathlib.Path:
    """Copy the agent's tree somewhere safe, then overwrite the held-out files.

    Grading never runs in the agent's own directory: the agent may have left a
    modified test file, a stale binary, or a `go.sum` that only works there.
    """
    stage = pathlib.Path(tempfile.mkdtemp(prefix="goturbo-grade-"))
    shutil.copytree(run_dir, stage, dirs_exist_ok=True)

    holdout = task_dir / "holdout"
    if holdout.is_dir():
        for src in holdout.rglob("*"):
            if src.is_file():
                dst = stage / src.relative_to(holdout)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    return stage


def grade_with_script(
    run_dir: pathlib.Path,
    task_dir: pathlib.Path,
    script: str,
    timeout: int = 900,
) -> GradeResult:
    # Resolve before staging: the grader runs with cwd set to the stage
    # directory, so a relative task path would not resolve from inside it.
    task_dir = task_dir.resolve()
    stage = _stage_for_grading(run_dir, task_dir)
    script_path = task_dir / script
    try:
        proc = subprocess.run(
            ["bash", str(script_path)],
            cwd=stage,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "TASK_DIR": str(task_dir), "STAGE_DIR": str(stage)},
        )
        raw = proc.stdout.strip()
        # The grader may print diagnostics before its verdict; take the last
        # JSON object on stdout.
        obj = None
        for line in reversed(raw.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if obj is None:
            return GradeResult(0.0, False, {}, f"grader emitted no JSON verdict\n{proc.stderr[-2000:]}")
        return GradeResult(
            obj.get("score", 0.0),
            obj.get("passed", False),
            obj.get("metrics", {}),
            obj.get("detail", ""),
        )
    except subprocess.TimeoutExpired:
        return GradeResult(0.0, False, {}, f"grader timed out after {timeout}s")
    finally:
        shutil.rmtree(stage, ignore_errors=True)


JUDGE_PROMPT = """\
You are grading one candidate answer against a fixed rubric. You are not \
comparing it to anything else, and you are not told which system produced it.

Score each rubric item independently. An item is met only if the answer \
actually states it; do not give credit for something a knowledgeable reader \
could infer. Do not reward length, confidence, or formatting.

Apply every penalty that fires. Penalties exist to catch answers that look \
authoritative while being wrong.

<rubric>
{rubric}
</rubric>

<candidate_answer>
{answer}
</candidate_answer>

Score every scored section of the rubric, whatever those sections are called.
`max_points` is the sum of the weights of every item in every scored section,
whether or not the answer met it. Penalties are not part of `max_points`.

Reply with one JSON object and nothing else:

{{"items": [{{"id": "<item id>", "section": "<section name>", "met": true|false, "why": "<8 words max>"}}],
  "penalties": [{{"id": "<penalty id>", "fired": true|false}}],
  "earned_points": <sum of weights of ALL met items, across every section>,
  "penalty_points": <sum of weights of FIRED penalties>,
  "max_points": <sum of weights of ALL items, across every section>}}
"""


def grade_with_judge(
    answer: str,
    rubric: str,
    judge_model: str,
    repeats: int = 3,
    timeout: int = 900,
) -> GradeResult:
    """Score one answer against a rubric with a pinned judge, averaged over draws."""
    prompt = JUDGE_PROMPT.format(rubric=rubric, answer=answer)
    draws: list[float] = []
    details: list[dict[str, Any]] = []
    anomalies: list[str] = []

    def one_draw(attempts: int = 3) -> dict[str, Any] | None:
        """One independent judge call, retried on transient failure.

        Judge invocations fail intermittently under load with a non-zero exit
        and no stderr. Those are transient, not verdicts, so retry with backoff
        rather than discarding the draw — a lost draw silently shrinks the
        sample the score is averaged over.
        """
        for attempt in range(attempts):
            obj = _one_draw_once()
            if obj is not None:
                return obj
            if attempt < attempts - 1:
                time.sleep(2 ** attempt * 5 + random.uniform(0, 3))
        return None

    def _one_draw_once() -> dict[str, Any] | None:
        with _judge_slots:
            try:
                proc = subprocess.run(
                    [
                        "claude", "-p",
                        "--model", judge_model,
                        "--safe-mode",
                        "--output-format", "json",
                        "--no-session-persistence",
                        prompt,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                anomalies.append(f"judge call timed out after {timeout}s")
                return None
            if proc.returncode != 0:
                anomalies.append(f"judge exited {proc.returncode}: {proc.stderr[-200:]}")
                return None
            try:
                envelope = json.loads(proc.stdout)
            except json.JSONDecodeError:
                anomalies.append(f"judge stdout not JSON: {proc.stdout[:200]!r}")
                return None
            if envelope.get("is_error"):
                anomalies.append(f"judge reported error: {str(envelope.get('result'))[:200]}")
                return None
            obj = _extract_json(str(envelope.get("result", "")))
            if obj is None:
                anomalies.append(f"no JSON object in judge reply: {str(envelope.get('result'))[:200]!r}")
            return obj

    # Draws are independent, so run them concurrently. Serially, three draws
    # per answer dominates the wall time of an entire grading pass.
    with concurrent.futures.ThreadPoolExecutor(max_workers=repeats) as pool:
        raw_objs = list(pool.map(lambda _: one_draw(), range(repeats)))

    for obj in raw_objs:
        try:
            if obj is None:
                continue

            earned = float(obj.get("earned_points", 0.0))
            penalty = float(obj.get("penalty_points", 0.0))
            max_points = float(obj.get("max_points", 0.0))

            # Every scored tier sits in the denominator, so a merely complete
            # answer lands well below 1.0 and the harder tiers provide real
            # headroom. An earlier version put only the required items in the
            # denominator; every strong answer pinned to exactly 1.0 and the
            # task measured nothing at all.
            if max_points <= 0:
                anomalies.append("judge reported non-positive max_points")
                continue
            if earned > max_points:
                anomalies.append(f"judge exceeded rubric maximum ({earned}/{max_points})")

            draws.append(max(0.0, min(1.0, (earned - penalty) / max_points)))
            details.append(obj)
        except (ValueError, TypeError):
            anomalies.append("judge verdict had non-numeric point totals")
            continue

    if not draws:
        return GradeResult(
            0.0, False, {"anomalies": anomalies},
            "GRADING FAILED (not a score): " + "; ".join(anomalies[:3]),
            error=True,
        )

    avg = sum(draws) / len(draws)
    spread = max(draws) - min(draws)
    first = details[0] if details else {}
    return GradeResult(
        avg,
        avg >= 0.5,
        {
            "judge_draws": [round(d, 4) for d in draws],
            "judge_spread": round(spread, 4),
            "judge_model": judge_model,
            "judge_repeats_parsed": len(draws),
            "earned_points": first.get("earned_points"),
            "max_points": first.get("max_points"),
            "penalty_points": first.get("penalty_points"),
            "anomalies": anomalies,
        },
        json.dumps(first.get("items", []))[:4000],
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model reply, fenced or bare."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None
