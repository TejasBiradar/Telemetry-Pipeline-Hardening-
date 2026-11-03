"""Aggregate daily delivery into campaign × channel performance."""

from __future__ import annotations

import pandas as pd
from metrics import cpc, cpm, ctr


def rollup(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 4: sum delivery and recompute efficiency at campaign/channel grain."""
    summary = (
        df.groupby(["campaign_id", "channel"])
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            spend_usd=("spend_usd", "sum"),
            conversions=("conversions", "sum"),
            row_count=("row_id", "count"),
        )
        .reset_index()
    )
    summary["cpm"] = cpm(summary["spend_usd"], summary["impressions"])
    summary["cpc"] = cpc(summary["spend_usd"], summary["clicks"].where(summary["clicks"] > 0))
    summary["ctr"] = ctr(summary["clicks"], summary["impressions"])
    summary["cost_per_conversion"] = summary["spend_usd"] / summary["conversions"].where(
        summary["conversions"] > 0
    )
    return summary
