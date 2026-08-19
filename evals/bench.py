#!/usr/bin/env python3
"""go-turbo eval suite.

Runs any model, in any arm, against the task suite, and reports scores with
error bars.

    ./evals/bench.py run    --model opus:xhigh --arm plain --arm skill --repeat 3
    ./evals/bench.py grade
    ./evals/bench.py report

Subcommands are separate so an expensive run is graded and re-reported without
re-running the models. `run` is resumable: it skips any (task, model, arm,
repeat) whose record already exists unless --force is given.

Standard library only.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from harness import grading, runner, stats  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
SUITE_PATH = ROOT / "suite.json"
RESULTS = ROOT / "results"
RUNS_PATH = RESULTS / "runs.jsonl"
GRADES_PATH = RESULTS / "grades.jsonl"
WORK_ROOT = RESULTS / "work"


def load_suite() -> dict[str, Any]:
    return json.loads(SUITE_PATH.read_text())


def load_tasks(suite: dict[str, Any], only: list[str] | None) -> list[dict[str, Any]]:
    tasks = []
    for name in suite["tasks"]:
        if only and name not in only:
            continue
        task_dir = ROOT / "tasks" / name
        spec = json.loads((task_dir / "task.json").read_text())
        spec["name"] = name
        spec["dir"] = task_dir
        tasks.append(spec)
    return tasks


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_jsonl(path: pathlib.Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


# --------------------------------------------------------------------------- run


def cmd_run(args: argparse.Namespace) -> int:
    suite = load_suite()
    tasks = load_tasks(suite, args.task)
    if not tasks:
        print("no tasks selected", file=sys.stderr)
        return 1

    models = [runner.ModelSpec(m) for m in (args.model or suite["defaults"]["models"])]
    arm_names = args.arm or suite["defaults"]["arms"]
    arms = [runner.Arm(n, suite["arms"][n], REPO_ROOT) for n in arm_names]

    done = {r["run_id"] for r in read_jsonl(RUNS_PATH)} if not args.force else set()

    pending: list[tuple[runner.Run, dict[str, Any]]] = []
    for task in tasks:
        for model in models:
            for arm in arms:
                for rep in range(1, args.repeat + 1):
                    run = runner.Run(task["name"], model, arm, rep)
                    if run.run_id in done:
                        continue
                    pending.append((run, task))

    if not pending:
        print("nothing to do; all runs already recorded (use --force to redo)")
        return 0

    total_cells = len(tasks) * len(models) * len(arms)
    print(
        f"{len(pending)} runs pending "
        f"({len(tasks)} tasks x {len(models)} models x {len(arms)} arms x {args.repeat} repeats, "
        f"{total_cells} cells), {args.jobs} at a time"
    )
    if args.repeat < 2:
        print(
            "  note: --repeat 1 gives no within-cell variance estimate. "
            "Use 3+ before drawing conclusions from small differences.",
            file=sys.stderr,
        )

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(
                runner.execute, run, task["dir"], WORK_ROOT,
                task.get("timeout_seconds", suite["defaults"]["timeout_seconds"]),
            ): run
            for run, task in pending
        }
        for fut in concurrent.futures.as_completed(futures):
            run = futures[fut]
            try:
                record = fut.result()
            except Exception as exc:  # a harness fault, not an agent failure
                record = {
                    "run_id": run.run_id, "task": run.task, "model": run.model.raw,
                    "arm": run.arm.name, "repeat": run.repeat,
                    "success": False, "harness_error": repr(exc),
                }
            append_jsonl(RUNS_PATH, record)
            completed += 1
            flag = "ok " if record.get("success") else "FAIL"
            print(
                f"[{completed}/{len(pending)}] {flag} {run.run_id} "
                f"${record.get('cost_usd', 0):.3f} {record.get('total_tokens', 0):,}tok "
                f"{record.get('wall_seconds', 0):.0f}s"
            )
    return 0


# ------------------------------------------------------------------------- grade


def cmd_grade(args: argparse.Namespace) -> int:
    suite = load_suite()
    tasks = {t["name"]: t for t in load_tasks(suite, args.task)}
    runs = read_jsonl(RUNS_PATH)
    graded = {g["run_id"] for g in read_jsonl(GRADES_PATH)} if not args.force else set()

    todo = [r for r in runs if r["task"] in tasks and r["run_id"] not in graded]
    if not todo:
        print("nothing to grade")
        return 0

    # Tasks whose score depends on a timing measurement must be graded one at a
    # time. Grading them alongside other work puts the benchmark under
    # unpredictable machine load, which is exactly the error that makes
    # cross-run timings incomparable.
    exclusive = [r for r in todo if tasks[r["task"]].get("exclusive")]
    parallel = [r for r in todo if not tasks[r["task"]].get("exclusive")]

    print(
        f"grading {len(todo)} runs: {len(parallel)} at {args.jobs} at a time, "
        f"{len(exclusive)} serially (timing-sensitive)"
    )

    def grade_one(record: dict[str, Any]) -> dict[str, Any]:
        task = tasks[record["task"]]
        kind = task["grader"]["kind"]
        if not record.get("success"):
            res = grading.GradeResult(0.0, False, {}, "run did not complete")
        elif kind == "script":
            res = grading.grade_with_script(
                pathlib.Path(record["work_dir"]), task["dir"],
                task["grader"]["script"],
                task["grader"].get("timeout_seconds", 900),
            )
        elif kind == "judge":
            rubric = (task["dir"] / task["grader"]["rubric"]).read_text()
            res = grading.grade_with_judge(
                record.get("answer", ""), rubric,
                suite["judge"]["model"],
                suite["judge"].get("repeats", 3),
            )
        else:
            raise ValueError(f"unknown grader kind {kind!r}")
        return {"run_id": record["run_id"], "task": record["task"],
                "model": record["model"], "arm": record["arm"],
                "repeat": record["repeat"], **res.to_dict()}

    done = 0

    failed: list[str] = []

    def record(grade: dict[str, Any]) -> None:
        nonlocal done
        done += 1
        if grade.get("error"):
            # Do NOT persist a failed grading as a score. It would be
            # indistinguishable from a genuine zero and would silently bias
            # every comparison. Leave it ungraded so a re-run retries it.
            failed.append(grade["run_id"])
            print(f"[{done}/{len(todo)}] {grade['run_id']} GRADING FAILED - not recorded")
            print(f"      {grade.get('detail','')[:160]}")
            return
        append_jsonl(GRADES_PATH, grade)
        print(f"[{done}/{len(todo)}] {grade['run_id']} score={grade['score']:.3f}")

    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for grade in pool.map(grade_one, parallel):
                record(grade)
    for r in exclusive:
        record(grade_one(r))

    if failed:
        print(f"\n{len(failed)} run(s) could not be graded and were left ungraded.")
        print("Re-run `bench.py grade` to retry them; they are not counted as zeros.")
    return 0


# ------------------------------------------------------------------------ report


def cmd_report(args: argparse.Namespace) -> int:
    suite = load_suite()
    grades = read_jsonl(GRADES_PATH)
    runs = {r["run_id"]: r for r in read_jsonl(RUNS_PATH)}
    if not grades:
        print("no grades yet; run `bench.py grade` first", file=sys.stderr)
        return 1

    models = sorted({g["model"] for g in grades})
    arms = sorted({g["arm"] for g in grades})
    tasks = sorted({g["task"] for g in grades})

    print("=" * 78)
    print("go-turbo eval report")
    print("=" * 78)
    print(f"tasks {len(tasks)}   models {len(models)}   arms {len(arms)}   graded runs {len(grades)}")
    print(f"judge: {suite['judge']['model']} x{suite['judge'].get('repeats', 3)} (rubric tasks only)")
    print()

    summaries: dict[tuple[str, str], stats.ArmSummary] = {}
    for model in models:
        for arm in arms:
            cells = []
            for task in tasks:
                scores = [
                    g["score"] for g in grades
                    if g["model"] == model and g["arm"] == arm and g["task"] == task
                ]
                if scores:
                    cells.append(stats.Cell(task, scores))
            if cells:
                summaries[(model, arm)] = stats.ArmSummary(f"{model} / {arm}", cells)

    print("-" * 78)
    print("SCORES  (mean over tasks, cluster-robust SE, 95% CI)")
    print("-" * 78)
    print(f"{'model / arm':<34}{'score':>9}{'SE':>8}{'95% CI':>20}{'runs':>7}")
    for (model, arm), s in sorted(summaries.items()):
        lo, hi = s.ci(0.95)
        ci = f"[{lo:.3f}, {hi:.3f}]" if lo == lo else "n/a"
        print(f"{s.label:<34}{s.mean:>9.3f}{s.stderr:>8.3f}{ci:>20}{s.total_runs:>7}")
    print()

    print("-" * 78)
    print("PER-TASK SCORES")
    print("-" * 78)
    header = f"{'task':<22}" + "".join(f"{m + '/' + a:>18}" for m, a in sorted(summaries))
    print(header)
    saturated: list[str] = []
    for task in tasks:
        row = f"{task:<22}"
        cell_means = []
        for key in sorted(summaries):
            cell = next((c for c in summaries[key].cells if c.task == task), None)
            row += f"{cell.mean:>18.3f}" if cell else f"{'-':>18}"
            if cell:
                cell_means.append(cell.mean)
        # A task where every arm lands at the ceiling (or the floor) carries no
        # information about the difference between arms, and it is worse than
        # useless: it contributes a zero to the vector of paired differences,
        # shrinking the estimated variance and making the comparison look more
        # precise than the evidence supports.
        if cell_means and (min(cell_means) >= 0.95 or max(cell_means) <= 0.05):
            saturated.append(task)
            row += "   <- saturated"
        print(row)
    print()

    if saturated:
        print(f"WARNING: {len(saturated)}/{len(tasks)} task(s) saturated: {', '.join(saturated)}")
        print("  Every arm scored at the ceiling or floor, so these tasks cannot")
        print("  distinguish the arms. They also deflate the paired standard error")
        print("  below, which overstates the precision of the comparison. Treat the")
        print("  effective task count as", len(tasks) - len(saturated), "and make these tasks harder.")
        print()

    print("-" * 78)
    print("COST AND TOKENS  (mean per run)")
    print("-" * 78)
    print(f"{'model / arm':<34}{'$/run':>10}{'tokens/run':>14}{'turns':>8}")
    for (model, arm) in sorted(summaries):
        rs = [runs[g["run_id"]] for g in grades
              if g["model"] == model and g["arm"] == arm and g["run_id"] in runs]
        if not rs:
            continue
        n = len(rs)
        print(
            f"{model + ' / ' + arm:<34}"
            f"{sum(r.get('cost_usd', 0) for r in rs) / n:>10.3f}"
            f"{sum(r.get('total_tokens', 0) for r in rs) / n:>14,.0f}"
            f"{sum(r.get('turns', 0) for r in rs) / n:>8.1f}"
        )
    print()

    if len(arms) >= 2:
        print("-" * 78)
        print("PAIRED ARM COMPARISON  (per-task differences, within each model)")
        print("-" * 78)
        for model in models:
            for i, a in enumerate(arms):
                for b in arms[i + 1:]:
                    ka, kb = (model, a), (model, b)
                    if ka not in summaries or kb not in summaries:
                        continue
                    cmp_ = stats.PairedComparison(summaries[ka], summaries[kb])
                    if cmp_.n < 2:
                        continue
                    lo, hi = cmp_.ci(0.95)
                    p = stats.sign_test_p(cmp_.diffs)
                    verdict = "SIGNIFICANT" if cmp_.significant(0.95) else "not significant"
                    print(f"\n{model}:  {a} - {b}")
                    print(f"  mean difference   {cmp_.mean_diff:+.3f}  (SE {cmp_.stderr:.3f})")
                    print(f"  95% CI            [{lo:+.3f}, {hi:+.3f}]  -> {verdict}")
                    print(f"  sign test p       {p:.3f}   (n={cmp_.n} tasks)")
                    mde = cmp_.min_detectable_effect()
                    if mde == mde:
                        print(f"  min detectable    {mde:.3f} at 80% power")
                        if not cmp_.significant(0.95):
                            need = cmp_.required_tasks(0.05)
                            if need == need:
                                print(f"  to resolve 0.05   ~{need:.0f} tasks needed")
                            print("  NOTE: a null result here is not equivalence. Any true")
                            print(f"        difference below {mde:.3f} is invisible at this suite size.")
        print()

    print("-" * 78)
    print("PROCESS METRICS  (skill loading; the outcome score cannot show this)")
    print("-" * 78)
    for (model, arm) in sorted(summaries):
        rs = [runs[g["run_id"]] for g in grades
              if g["model"] == model and g["arm"] == arm and g["run_id"] in runs]
        if not rs:
            continue
        invoked = sum(1 for r in rs if r.get("skills_invoked"))
        names: dict[str, int] = {}
        refs: dict[str, int] = {}
        for r in rs:
            for s in r.get("skills_invoked", []):
                names[s] = names.get(s, 0) + 1
            for p in r.get("skill_files_read", []):
                refs[pathlib.Path(p).name] = refs.get(pathlib.Path(p).name, 0) + 1
        print(f"\n{model} / {arm}: skill invoked in {invoked}/{len(rs)} runs")
        if names:
            print(f"  skills: {dict(sorted(names.items(), key=lambda kv: -kv[1]))}")
        print(f"  skill files read: {dict(sorted(refs.items(), key=lambda kv: -kv[1])) or 'NONE'}")
    print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="execute runs")
    r.add_argument("--model", action="append",
                   help="model spec, repeatable: 'opus', 'sonnet:high', 'claude-opus-5:xhigh'")
    r.add_argument("--arm", action="append", help="arm name from suite.json, repeatable")
    r.add_argument("--task", action="append", help="restrict to these tasks")
    r.add_argument("--repeat", type=int, default=3, help="repeats per cell (default 3)")
    r.add_argument("--jobs", type=int, default=4, help="concurrent runs (default 4)")
    r.add_argument("--force", action="store_true", help="re-run already-recorded runs")
    r.set_defaults(func=cmd_run)

    g = sub.add_parser("grade", help="grade completed runs")
    g.add_argument("--task", action="append")
    g.add_argument("--jobs", type=int, default=4)
    g.add_argument("--force", action="store_true")
    g.set_defaults(func=cmd_grade)

    p = sub.add_parser("report", help="print the statistical report")
    p.set_defaults(func=cmd_report)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
