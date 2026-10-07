"""Per-segment volume: catches a client version going silent or dropping sharply, which no
value-level check can see (an absent segment never appears in a `groupby`)."""

from __future__ import annotations

import pandas as pd

from teleguard.drift.baseline import BaselineStore
from teleguard.models import BatchContext, CheckResult, CheckType, Status


class SegmentVolumeCheck:
    check_type = CheckType.VOLUME

    def __init__(self, checkpoint: str, baselines: BaselineStore,
                min_share_of_baseline: float = 0.5) -> None:
        self.checkpoint = checkpoint
        self.baselines = baselines
        self.min_share_of_baseline = min_share_of_baseline
        self.name = "segment_volume"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        known = self.baselines.known_segments(self.checkpoint)
        if not known:
            return [CheckResult(check=self.name, check_type=self.check_type,
                               checkpoint=self.checkpoint, status=Status.INSUFFICIENT_DATA,
                               message="no segment-volume baseline yet")]
        if not ctx.segment_column or ctx.segment_column not in df.columns:
            return [CheckResult(check=self.name, check_type=self.check_type,
                               checkpoint=self.checkpoint, status=Status.ERROR,
                               message="no segment column to count by")]
        present = df[ctx.segment_column].astype(str).value_counts().to_dict()
        results = []
        for segment in known:
            baseline = self.baselines.segment_volume_for(self.checkpoint, segment)
            if baseline is None or baseline.median <= 0:
                continue
            current = present.get(segment, 0)
            share = current / baseline.median
            status = Status.PASS if share >= self.min_share_of_baseline else Status.FAIL
            results.append(CheckResult(
                check=self.name, check_type=self.check_type, checkpoint=self.checkpoint,
                status=status, segment=segment,
                message="" if status is Status.PASS else
                (f"'{segment}' silent this batch" if current == 0 else
                 f"'{segment}' volume is {share:.0%} of its usual {baseline.median:.0f} rows"),
                details={"current": current, "baseline_median": baseline.median, "share": share}))
        return results
