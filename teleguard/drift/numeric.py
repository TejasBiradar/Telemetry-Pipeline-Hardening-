"""Numeric drift: PSI (shape/snapshot) and the Kolmogorov-Smirnov test (statistical
significance), each batch compared against the frozen baseline sample, per segment.

Two methods, not five (ADR-6): precision and recall are only half the story under
questioning — being able to explain *why* a method was chosen matters as much, so this
covers two well enough to defend rather than five shallowly. Wasserstein/EWMA/CUSUM are
natural additions later (see teleguard/drift/numeric.py docstring in review notes) and
slot into the same `Check` interface without changing anything else.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy import stats

from teleguard.checks.base import MIN_SAMPLE_SIZE, segments
from teleguard.drift.baseline import BaselineStore, NumericBaseline
from teleguard.models import BatchContext, CheckResult, CheckType, Status

_EPS = 1e-6
_PSI_BINS = 10
_Score = Callable[[NumericBaseline, "pd.Series[float]"], tuple[float, bool]]


def _psi(baseline_sample: tuple[float, ...], current: np.ndarray) -> float:
    ref = np.asarray(baseline_sample, dtype=float)
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, _PSI_BINS + 1)))
    if len(edges) < 3:  # baseline has almost no spread: binning can't say anything useful
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_counts, _ = np.histogram(ref, bins=edges)
    cur_counts, _ = np.histogram(current, bins=edges)
    ref_pct = ref_counts / ref_counts.sum() + _EPS
    cur_pct = cur_counts / cur_counts.sum() + _EPS
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


class PsiCheck:
    check_type = CheckType.NUMERIC_DRIFT

    def __init__(self, checkpoint: str, field: str, baselines: BaselineStore,
                threshold: float = 0.10) -> None:
        self.checkpoint = checkpoint
        self.field = field
        self.baselines = baselines
        self.threshold = threshold
        self.name = f"psi:{field}"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        return _run_numeric(self, df, ctx, self._score)

    def _score(self, baseline: NumericBaseline, values: pd.Series) -> tuple[float, bool]:
        psi = _psi(baseline.sample, values.to_numpy(dtype=float))
        return psi, psi <= self.threshold


class KsCheck:
    """Rejects on p-value *and* a minimum effect size (the D-statistic): at large batch
    sizes KS-test flags trivially small differences as "significant" (BUILD_PLAN.md §... /
    ADR-6 known limitation), so p-value alone is not a safe gate."""

    check_type = CheckType.NUMERIC_DRIFT

    def __init__(self, checkpoint: str, field: str, baselines: BaselineStore,
                alpha: float = 0.01, min_statistic: float = 0.1) -> None:
        self.checkpoint = checkpoint
        self.field = field
        self.baselines = baselines
        self.alpha = alpha
        self.min_statistic = min_statistic
        self.name = f"ks:{field}"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        return _run_numeric(self, df, ctx, self._score)

    def _score(self, baseline: NumericBaseline, values: pd.Series) -> tuple[float, bool]:
        result = stats.ks_2samp(np.asarray(baseline.sample, dtype=float),
                               values.to_numpy(dtype=float))
        significant = result.pvalue < self.alpha and result.statistic >= self.min_statistic
        return float(result.statistic), not significant


def _run_numeric(check: PsiCheck | KsCheck, df: pd.DataFrame, ctx: BatchContext,
                 score: _Score) -> list[CheckResult]:
    if check.field not in df.columns:
        return [CheckResult(check=check.name, check_type=CheckType.NUMERIC_DRIFT,
                           checkpoint=check.checkpoint, status=Status.ERROR, field=check.field,
                           message=f"'{check.field}' is missing from this batch")]
    results = []
    for segment, part in segments(df, ctx):
        baseline = check.baselines.numeric_for(check.checkpoint, check.field, segment)
        values = part[check.field].dropna()
        if baseline is None:
            results.append(CheckResult(
                check=check.name, check_type=CheckType.NUMERIC_DRIFT, checkpoint=check.checkpoint,
                status=Status.INSUFFICIENT_DATA, field=check.field, segment=segment,
                message="no baseline for this field/segment yet"))
            continue
        if len(values) < MIN_SAMPLE_SIZE:
            results.append(CheckResult(
                check=check.name, check_type=CheckType.NUMERIC_DRIFT, checkpoint=check.checkpoint,
                status=Status.INSUFFICIENT_DATA, field=check.field, segment=segment,
                message=f"only {len(values)} rows, below the minimum of {MIN_SAMPLE_SIZE}"))
            continue
        value, passed = score(baseline, values)
        status = Status.PASS if passed else Status.FAIL
        results.append(CheckResult(
            check=check.name, check_type=CheckType.NUMERIC_DRIFT, checkpoint=check.checkpoint,
            status=status, field=check.field, segment=segment,
            message="" if passed else f"{check.name.split(':')[0].upper()} score {value:.3f} "
            "indicates the distribution has drifted from baseline",
            details={"score": value}))
    return results
