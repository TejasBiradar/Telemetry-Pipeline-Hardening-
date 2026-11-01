"""Add fields that reconcile groups on."""

from __future__ import annotations

import pandas as pd
from rules import merchant_region


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Derive merchant region and transaction date."""
    df = df.copy()
    df["transaction_date"] = pd.to_datetime(df["event_ts"]).dt.date
    df["merchant_region"] = df["merchant_id"].map(merchant_region)
    return df
