"""Drop rows the later stages cannot use, and convert cents to dollars."""

from __future__ import annotations

import pandas as pd
from rules import allowed_status, flag_error, to_usd


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Dedupe, drop null users, convert cents to USD, and keep known statuses."""
    df = df.drop_duplicates(subset=["transaction_id"], keep="first")
    df = df[df["user_id"].notna()].copy()
    df = df[(df["amount_cents"] > 0) & (df["amount_cents"] < 99_999_999)].copy()
    df["amount_usd"] = to_usd(df["amount_cents"])
    df["is_error"] = flag_error(df["error_message"])
    df = df[df["status"].isin(allowed_status())].copy()
    return df
