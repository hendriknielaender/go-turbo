# go-turbo eval suite

Measures whether loading `go-turbo` changes what a coding agent produces, for
any model the Claude Code CLI accepts.

```sh
./evals/bench.py run --model opus:xhigh --arm plain --arm skill --repeat 3
./evals/bench.py grade
./evals/bench.py report
```

`run`, `grade`, and `report` are separate so an expensive run can be re-graded
and re-reported without re-running any models. `run` is resumable and skips
work already recorded in `results/runs.jsonl`.

## Running any model

`--model` is passed through to the CLI, so anything it accepts is valid. Append
`:effort` to set the effort level.

```sh
# one model, both arms
./evals/bench.py run --model sonnet:high

# several models at once; every model runs every arm
./evals/bench.py run --model opus:xhigh --model sonnet:high --model haiku

# a pinned model id
./evals/bench.py run --model claude-opus-5:max

# isolate skill content quality from skill triggering
./evals/bench.py run --arm skill --arm skill-forced
```

Arms live in `suite.json`. An arm may add process-level flags — a plugin
directory, an appended system prompt — but never task text; the harness sends
byte-identical prompts to every arm so that any difference is attributable to
the arm and not to the wording.

## Methodology

The design follows Miller, [*Adding Error Bars to Evals*](https://arxiv.org/abs/2411.00640)
(arXiv:2411.00640), and the task/outcome validity guidance in
[*Establishing Best Practices for Building Rigorous Agentic Benchmarks*](https://arxiv.org/abs/2507.02825)
(arXiv:2507.02825).

**Repeats and variance.** Agents are stochastic; a single run per cell measures
one draw, not a capability. `--repeat` defaults to 3 and the harness warns at
`--repeat 1`. Averaging K repeats divides the within-task variance by K.

**Cluster-robust standard errors.** Repeats of the same task are correlated, so
pooling every run as an independent observation would understate the error by
roughly `sqrt(K)`. The reported score is the unweighted mean of per-task means,
and the standard error is computed *between* tasks.

**Paired comparison.** Arms are compared on per-task differences rather than by
subtracting two independent means. Task difficulty dominates the variance on a
suite this small, and pairing cancels it. The report also prints an exact sign
test, which assumes nothing about the shape of the distribution — worth having
when n is a handful of tasks and the normal approximation is doing real work.

**Power, and what a null result means.** Every non-significant comparison
prints the minimum detectable effect at 80% power and the number of tasks
needed to resolve a 0.05 difference. A null result on four tasks is not
evidence of equivalence; it is usually evidence that the suite is too small.
This is the single easiest way to over-claim from an eval, so the report states
it rather than leaving it to the reader.

**Outcome validity.** Before any script grader runs, every file in the task's
`holdout/` directory is copied over the agent's tree. An agent that deleted,
weakened, or rewrote the contract tests is graded against the originals.
Grading happens in a copy, never in the agent's own directory.

**Timing validity.** `logfmt-hotpath` re-measures its own baseline back-to-back
with the candidate, in the same grading pass on the same machine, instead of
comparing against a stored number. Benchmark figures taken under different
machine load are not comparable. Tasks marked `"exclusive": true` are graded
serially for the same reason.

**Judge controls.** Tasks whose product is a judgement rather than an artifact
are scored by a pinned model against a fixed rubric, with these controls:

- *Pointwise, never pairwise.* The judge sees one answer at a time and is never
  told which arm or model produced it. There is no position to be biased by and
  no arm identity to prefer. Pairwise judging shows a well-documented
  first-slot preference worth 10–15 points; this design has no slots.
- *Enumerated rubric items with weights*, scored individually, rather than a
  holistic score — which limits the verbosity and confident-tone preferences
  that holistic judging rewards.
- *Explicit penalties*, so an answer that is fluent and wrong scores below one
  that is terse and right.
- *Repeated draws.* The judge is sampled `judge.repeats` times and averaged; a
  single judge call is itself a noisy measurement. The spread is recorded.
- *A pinned judge model*, recorded in every result. Changing it moves every
  rubric score, so re-grade the whole suite when you do.

Prefer a judge from outside the family under test. When that is not possible,
treat rubric-task deltas as weaker evidence than script-task deltas: the two
script tasks are graded by the Go toolchain and are immune to judge bias
entirely.

**Contamination.** All four fixtures were written for this suite. They are not
derived from any public benchmark, issue tracker, or repository, so they cannot
appear in a pretraining corpus. Each task records its provenance in
`task.json`. Fixtures are original in the sense that matters — nothing about
them is retrievable from memory — but note that the *techniques* they reward
are common knowledge, which is the point: the suite measures whether an agent
applies them here, not whether it knows them.

**Process metrics.** The report prints skill invocation counts and which skill
files were actually read. An outcome score cannot distinguish "the skill helped"
from "the skill never loaded," and that distinction is usually the finding.

## Tasks

| task | grader | probes |
|---|---|---|
| `dedup-implement` | script | complexity class under a wide input range, nil semantics, no input mutation |
| `config-restraint` | judge | restraint against five confidently-worded but unjustified demands |
| `logfmt-hotpath` | script | finds the real cost, holds a byte-exact output contract, measures its claim |
| `ingest-review` | judge | bounded concurrency, retry safety on a non-idempotent POST, read-only scope |

Two script-graded and two judge-graded is deliberate: the script tasks anchor
the suite in outcomes the toolchain can verify, and the judge tasks cover the
behaviors — restraint, calibration, scope discipline — that no test can express.

### Adding a task

Create `tasks/<name>/` with `task.json`, `prompt.md`, and `fixture/`. Add a
`holdout/` plus `grade.sh` for a script grader, or a `rubric.md` for a judge
grader. Register the name in `suite.json`.

Four tasks is enough to detect only large effects. The power analysis in the
report tells you how many you need for the effect you care about; adding tasks
is the highest-leverage change available to this suite.

Prompts must stay neutral. Never name the skill in `prompt.md` — the `skill`
arm has to trigger on its own description, and whether it does is a result. Use
the `skill-forced` arm to separate content quality from trigger reliability.

## Known limitations

Recorded here rather than discovered again later. Each one was observed while
building the suite.

**`dedup-implement` saturates.** Every arm scores 1.0, on models from Haiku
upward. A saturated task cannot distinguish arms, and it actively harms the
comparison by contributing a zero to the paired differences, which shrinks the
estimated variance and overstates precision. The report flags this. Hardening
the task — a stricter allocation budget, an adversarial input distribution, a
retention assertion — is the fix.

**The `ingest-review` discrimination tier was written after reading real
answers.** The required and bonus items were fixed in advance; the four
discrimination items were added after observing that defect enumeration
saturated. They are defensible as general review-quality criteria, but a rubric
item authored after seeing the outputs it must separate is at risk of encoding
one observation rather than a real capability difference. Treat that tier's
discriminating power as provisional until it is confirmed on runs that did not
inform its design.

**Skill triggering is model-dependent, and the outcome score cannot see it.**
With the plugin loaded and the prompt neutral, Opus invoked the skill on every
task; Haiku invoked it on none, while still paying for the skill descriptions
in its system prompt. A skill arm that never loads the skill is measuring the
base model with extra overhead. Always read the process-metrics section before
interpreting a score, and use `skill-forced` to separate content quality from
trigger reliability.

**Four tasks resolves only large effects.** With `--repeat 3` this suite
detects differences on the order of 0.1–0.2 in the paired score, not 0.05. The
report prints the minimum detectable effect for exactly this reason. More tasks
help far more than more repeats once K is 3.

## Layout

```text
evals/
├── bench.py              run | grade | report
├── suite.json            arms, judge, defaults, task list
├── harness/
│   ├── runner.py         run execution, model specs, transcript parsing
│   ├── grading.py        script graders, judge, holdout restoration
│   └── stats.py          CLT/clustered SE, paired inference, power
├── tasks/<name>/
│   ├── task.json         grader config, probes, provenance
│   ├── prompt.md         the exact prompt, identical across arms
│   ├── fixture/          starting tree, copied fresh per run
│   ├── holdout/          files restored over the agent's tree before grading
│   ├── baseline/         reference implementation for speedup measurement
│   └── grade.sh          script grader, emits one JSON verdict
└── results/              runs.jsonl, grades.jsonl, work/ (gitignored)
```

## Cost

Every run is a full agent session. A 4-task × 2-arm × 3-repeat sweep is 24 runs;
on a frontier model at high effort that is roughly $25–35 and about an hour at
`--jobs 4`. Scope with `--task` and `--model` while iterating, and raise
`--repeat` only for the comparison you intend to publish.
