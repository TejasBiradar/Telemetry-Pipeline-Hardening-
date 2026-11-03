"""Drop unusable rows and keep known channels only."""

from __future__ import annotations

import pandas as pd
from metrics import allowed_channels


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 2: filter null campaigns, non-positive delivery, and unknown channels."""
    df = df.drop_duplicates(subset=["row_id"], keep="first")
    df = df[df["campaign_id"].notna()].copy()
    df = df[(df["impressions"] > 0) & (df["spend_usd"] >= 0)].copy()
    df = df[df["clicks"] >= 0].copy()
    df = df[df["channel"].isin(allowed_channels())].copy()
    return df
