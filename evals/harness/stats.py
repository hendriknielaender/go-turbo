#!/usr/bin/env python3
"""Statistics for the go-turbo eval suite.

The methods here follow Miller, "Adding Error Bars to Evals" (arXiv:2411.00640):

1. Report standard errors of the mean, not bare point estimates.
2. When runs arrive in related groups, cluster the standard errors on the
   group. Repeats of the same task are not independent draws, so this suite
   clusters on the task.
3. Reduce conditional variance by resampling: K repeats per cell divide the
   within-task variance by K.
4. Compare two arms with inference on the *paired* per-task differences, which
   cancels the task-difficulty variance that dominates a small suite.
5. Use power analysis to state the effect size a suite of this size can
   actually resolve, so a null result is not mistaken for equivalence.

Standard library only, matching scripts/validate.py.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation).

    Accurate to about 1.15e-9 over the open unit interval, which is far beyond
    what these sample sizes justify. Implemented here rather than pulled from
    scipy so the suite keeps the repository's standard-library-only rule.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"norm_ppf requires 0 < p < 1, got {p}")

    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00)

    p_low, p_high = 0.02425, 1 - 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > p_high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def z_two_sided(confidence: float) -> float:
    """Critical value for a two-sided interval, e.g. 1.96 at 95%."""
    return norm_ppf(1.0 - (1.0 - confidence) / 2.0)


def z_power(power: float) -> float:
    """One-sided quantile for a target power, e.g. 0.8416 at 80%."""
    return norm_ppf(power)


def mean(xs: Sequence[float]) -> float:
    if not xs:
        return float("nan")
    return sum(xs) / len(xs)


def variance(xs: Sequence[float]) -> float:
    """Unbiased sample variance. Zero for a single observation."""
    n = len(xs)
    if n < 2:
        return 0.0
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (n - 1)


def stderr(xs: Sequence[float]) -> float:
    """Standard error of the mean via the CLT."""
    n = len(xs)
    if n < 2:
        return float("nan")
    return math.sqrt(variance(xs) / n)


class Cell:
    """All repeats of one (task, model, arm) combination."""

    def __init__(self, task: str, scores: Sequence[float]):
        self.task = task
        self.scores = list(scores)

    @property
    def k(self) -> int:
        return len(self.scores)

    @property
    def mean(self) -> float:
        return mean(self.scores)

    @property
    def within_var(self) -> float:
        """Conditional variance of a single repeat within this task."""
        return variance(self.scores)


class ArmSummary:
    """Cluster-robust summary of one arm across tasks.

    Each task is one cluster. The arm score is the unweighted mean of the
    per-task means, so a task with more repeats does not dominate, and the
    standard error is computed between clusters. This is recommendation 2:
    repeats inside a task are correlated, so pooling all runs as if they were
    independent would understate the error by roughly sqrt(K).
    """

    def __init__(self, label: str, cells: Iterable[Cell]):
        self.label = label
        self.cells = sorted(cells, key=lambda c: c.task)
        self.task_means = [c.mean for c in self.cells]

    @property
    def n_tasks(self) -> int:
        return len(self.cells)

    @property
    def total_runs(self) -> int:
        return sum(c.k for c in self.cells)

    @property
    def mean(self) -> float:
        return mean(self.task_means)

    @property
    def stderr(self) -> float:
        """Cluster-robust SE: between-task variance of the per-task means."""
        return stderr(self.task_means)

    @property
    def mean_within_var(self) -> float:
        """Average conditional variance, used for power analysis."""
        return mean([c.within_var for c in self.cells]) if self.cells else 0.0

    def ci(self, confidence: float = 0.95) -> tuple[float, float]:
        se = self.stderr
        if math.isnan(se):
            return (float("nan"), float("nan"))
        half = z_two_sided(confidence) * se
        return (self.mean - half, self.mean + half)


class PairedComparison:
    """Paired per-task comparison of two arms (recommendation 4).

    Both arms answer the same tasks, so the per-task difference removes the
    task-difficulty component. On a suite this small that is the difference
    between a usable test and noise.
    """

    def __init__(self, a: ArmSummary, b: ArmSummary):
        shared = sorted(set(c.task for c in a.cells) & set(c.task for c in b.cells))
        a_by_task = {c.task: c for c in a.cells}
        b_by_task = {c.task: c for c in b.cells}
        self.a = a
        self.b = b
        self.tasks = shared
        self.diffs = [a_by_task[t].mean - b_by_task[t].mean for t in shared]

    @property
    def n(self) -> int:
        return len(self.diffs)

    @property
    def mean_diff(self) -> float:
        return mean(self.diffs)

    @property
    def stderr(self) -> float:
        return stderr(self.diffs)

    @property
    def t_stat(self) -> float:
        se = self.stderr
        if math.isnan(se) or se == 0.0:
            return float("nan")
        return self.mean_diff / se

    def ci(self, confidence: float = 0.95) -> tuple[float, float]:
        se = self.stderr
        if math.isnan(se):
            return (float("nan"), float("nan"))
        half = z_two_sided(confidence) * se
        return (self.mean_diff - half, self.mean_diff + half)

    def significant(self, confidence: float = 0.95) -> bool:
        lo, hi = self.ci(confidence)
        if math.isnan(lo):
            return False
        return lo > 0.0 or hi < 0.0

    def min_detectable_effect(self, confidence: float = 0.95, power: float = 0.80) -> float:
        """Smallest true difference this suite could resolve (recommendation 5).

        Reported alongside every null result. A difference smaller than this is
        not evidence of equivalence, only of insufficient sample size.
        """
        se = self.stderr
        if math.isnan(se) or self.n < 2:
            return float("nan")
        return (z_two_sided(confidence) + z_power(power)) * se

    def required_tasks(self, delta: float, confidence: float = 0.95, power: float = 0.80) -> float:
        """Tasks needed to detect a true difference of `delta` at this variance.

        n = (z_a + z_b)^2 * var(d) / delta^2
        """
        if delta <= 0 or self.n < 2:
            return float("nan")
        var_d = variance(self.diffs)
        if var_d == 0.0:
            return 1.0
        return ((z_two_sided(confidence) + z_power(power)) ** 2) * var_d / (delta**2)


def sign_test_p(diffs: Sequence[float]) -> float:
    """Two-sided exact sign test.

    A distribution-free companion to the t-based interval. With a handful of
    tasks the normal approximation is doing real work, so a test that assumes
    nothing about the shape is a useful cross-check.
    """
    nonzero = [d for d in diffs if d != 0.0]
    n = len(nonzero)
    if n == 0:
        return 1.0
    wins = sum(1 for d in nonzero if d > 0)
    k = min(wins, n - wins)
    total = 0
    for i in range(0, k + 1):
        total += math.comb(n, i)
    p = 2.0 * total / (2**n)
    return min(1.0, p)
