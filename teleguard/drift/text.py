"""Text/payload drift: vocabulary shift (OOV rate) and template shift (new-template rate),
each batch compared against the frozen baseline, per segment.

Two methods, not four (ADR-7, same reasoning as teleguard/drift/numeric.py): chi-square over
template counts and embedding-based drift are natural additions later: they slot into the
same `Check` interface without changing anything else.
"""

from __future__ import annotations

import pandas as pd

from teleguard.checks.base import MIN_SAMPLE_SIZE, segments
from teleguard.drift.baseline import BaselineStore, mask_template, tokenize
from teleguard.models import BatchContext, CheckResult, CheckType, Status


class OovRateCheck:
    """Share of tokens in the current batch never seen in the baseline vocabulary."""

    check_type = CheckType.TEXT_DRIFT

    def __init__(self, checkpoint: str, field: str, baselines: BaselineStore,
                threshold: float = 0.15) -> None:
        self.checkpoint = checkpoint
        self.field = field
        self.baselines = baselines
        self.threshold = threshold
        self.name = f"oov_rate:{field}"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        if self.field not in df.columns:
            return [CheckResult(check=self.name, check_type=CheckType.TEXT_DRIFT,
                               checkpoint=self.checkpoint, status=Status.ERROR, field=self.field,
                               message=f"'{self.field}' is missing from this batch")]
        results = []
        for segment, part in segments(df, ctx):
            baseline = self.baselines.text_for(self.checkpoint, self.field, segment)
            values = part[self.field].dropna().astype(str)
            if baseline is None:
                results.append(CheckResult(
                    check=self.name, check_type=CheckType.TEXT_DRIFT, checkpoint=self.checkpoint,
                    status=Status.INSUFFICIENT_DATA, field=self.field, segment=segment,
                    message="no baseline for this field/segment yet"))
                continue
            if len(values) < MIN_SAMPLE_SIZE:
                results.append(CheckResult(
                    check=self.name, check_type=CheckType.TEXT_DRIFT, checkpoint=self.checkpoint,
                    status=Status.INSUFFICIENT_DATA, field=self.field, segment=segment,
                    message=f"only {len(values)} rows, below the minimum of {MIN_SAMPLE_SIZE}"))
                continue
            tokens = [token for text in values for token in tokenize(text)]
            rate = (sum(1 for t in tokens if t not in baseline.vocabulary) / len(tokens)
                   if tokens else 0.0)
            status = Status.PASS if rate <= self.threshold else Status.FAIL
            results.append(CheckResult(
                check=self.name, check_type=CheckType.TEXT_DRIFT, checkpoint=self.checkpoint,
                status=status, field=self.field, segment=segment,
                message="" if status is Status.PASS else
                f"{rate:.1%} of words are new versus the baseline vocabulary",
                details={"oov_rate": rate, "threshold": self.threshold, "tokens": len(tokens)}))
        return results


class TemplateDriftCheck:
    """Share of records whose masked template (numbers/ids replaced with <NUM>) never
    appeared in the baseline. Catches a new error type or log format even when individual
    words are all familiar."""

    check_type = CheckType.TEXT_DRIFT

    def __init__(self, checkpoint: str, field: str, baselines: BaselineStore,
                threshold: float = 0.30) -> None:
        self.checkpoint = checkpoint
        self.field = field
        self.baselines = baselines
        self.threshold = threshold
        self.name = f"template_drift:{field}"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        if self.field not in df.columns:
            return [CheckResult(check=self.name, check_type=CheckType.TEXT_DRIFT,
                               checkpoint=self.checkpoint, status=Status.ERROR, field=self.field,
                               message=f"'{self.field}' is missing from this batch")]
        results = []
        for segment, part in segments(df, ctx):
            baseline = self.baselines.text_for(self.checkpoint, self.field, segment)
            values = part[self.field].dropna().astype(str)
            if baseline is None:
                results.append(CheckResult(
                    check=self.name, check_type=CheckType.TEXT_DRIFT, checkpoint=self.checkpoint,
                    status=Status.INSUFFICIENT_DATA, field=self.field, segment=segment,
                    message="no baseline for this field/segment yet"))
                continue
            if len(values) < MIN_SAMPLE_SIZE:
                results.append(CheckResult(
                    check=self.name, check_type=CheckType.TEXT_DRIFT, checkpoint=self.checkpoint,
                    status=Status.INSUFFICIENT_DATA, field=self.field, segment=segment,
                    message=f"only {len(values)} rows, below the minimum of {MIN_SAMPLE_SIZE}"))
                continue
            new_templates = [mask_template(t) for t in values
                            if mask_template(t) not in baseline.template_counts]
            rate = len(new_templates) / len(values)
            status = Status.PASS if rate <= self.threshold else Status.WARN
            sample = sorted(set(new_templates))[:3]
            results.append(CheckResult(
                check=self.name, check_type=CheckType.TEXT_DRIFT, checkpoint=self.checkpoint,
                status=status, field=self.field, segment=segment,
                message="" if status is Status.PASS else
                f"{rate:.1%} of records match a template never seen in the baseline, "
                f"e.g. {sample}",
                details={"new_template_rate": rate, "threshold": self.threshold,
                        "sample_new_templates": sample}))
        return results
