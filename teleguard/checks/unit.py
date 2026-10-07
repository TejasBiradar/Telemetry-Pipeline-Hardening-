"""Unit-consistency check: catches a clean magnitude shift (ms<->s, cents<->dollars) that
shape-based drift detectors can miss.

A uniform x1000 shift of an entire distribution barely changes its *shape*, so PSI/KS can
stay quiet. This check instead compares a robust statistic (median, by default) of the
current batch against the frozen baseline, on a log scale: a real unit error produces a
characteristic log-ratio (x1000 -> ~3, x60 -> ~1.78), which a single distance threshold
struggles to express well on the raw scale.
"""

from __future__ import annotations

import math

import pandas as pd

from teleguard.checks.base import MIN_SAMPLE_SIZE, segments
from teleguard.drift.baseline import BaselineStore
from teleguard.models import BatchContext, CheckResult, CheckType, Status


class UnitConsistencyCheck:
    check_type = CheckType.UNIT

    def __init__(self, checkpoint: str, field: str, baselines: BaselineStore,
                baseline_stat: str = "median", log_ratio_threshold: float = 0.3) -> None:
        if baseline_stat not in ("median", "mean"):
            raise ValueError(f"baseline_stat must be 'median' or 'mean', got {baseline_stat!r}")
        self.checkpoint = checkpoint
        self.field = field
        self.baselines = baselines
        self.baseline_stat = baseline_stat
        self.log_ratio_threshold = log_ratio_threshold
        self.name = f"unit:{field}"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        if self.field not in df.columns:
            return [CheckResult(check=self.name, check_type=CheckType.UNIT,
                               checkpoint=self.checkpoint, status=Status.ERROR, field=self.field,
                               message=f"'{self.field}' is missing from this batch")]
        results = []
        for segment, part in segments(df, ctx):
            baseline = self.baselines.numeric_for(self.checkpoint, self.field, segment)
            values = part[self.field].dropna().astype(float)
            if baseline is None:
                results.append(CheckResult(
                    check=self.name, check_type=CheckType.UNIT, checkpoint=self.checkpoint,
                    status=Status.INSUFFICIENT_DATA, field=self.field, segment=segment,
                    message="no baseline for this field/segment yet"))
                continue
            if len(values) < MIN_SAMPLE_SIZE:
                results.append(CheckResult(
                    check=self.name, check_type=CheckType.UNIT, checkpoint=self.checkpoint,
                    status=Status.INSUFFICIENT_DATA, field=self.field, segment=segment,
                    message=f"only {len(values)} rows, below the minimum of {MIN_SAMPLE_SIZE}"))
                continue
            current = float(values.median() if self.baseline_stat == "median" else values.mean())
            reference = baseline.median if self.baseline_stat == "median" else baseline.mean
            if current <= 0 or reference <= 0:
                log_ratio = float("inf") if current != reference else 0.0
            else:
                log_ratio = math.log10(current / reference)
            status = Status.PASS if abs(log_ratio) <= self.log_ratio_threshold else Status.FAIL
            results.append(CheckResult(
                check=self.name, check_type=CheckType.UNIT, checkpoint=self.checkpoint,
                status=status, field=self.field, segment=segment,
                message="" if status is Status.PASS else
                f"{self.baseline_stat} moved by a factor of {10 ** log_ratio:.1f}x versus "
                "baseline: looks like a unit change, not ordinary drift",
                details={"log_ratio": log_ratio, "current": current, "baseline": reference,
                        "threshold": self.log_ratio_threshold}))
        return results
