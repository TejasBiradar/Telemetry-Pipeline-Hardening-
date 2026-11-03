"""Add unit-cost and efficiency metrics from spend and delivery."""

from __future__ import annotations

import pandas as pd
from metrics import cpc, cpm, ctr


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 3: compute CPM, CPC, and CTR on each delivery row."""
    df = df.copy()
    df["cpm"] = cpm(df["spend_usd"], df["impressions"])
    df["cpc"] = cpc(df["spend_usd"], df["clicks"].where(df["clicks"] > 0))
    df["ctr"] = ctr(df["clicks"], df["impressions"])
    df["cost_per_conversion"] = df["spend_usd"] / df["conversions"].where(
        df["conversions"] > 0
    )
    return df
