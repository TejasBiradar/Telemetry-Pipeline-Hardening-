"""Roll cleaned payments up by day, region, and method."""

from __future__ import annotations

import pandas as pd
from rules import is_declined


def reconcile(df: pd.DataFrame) -> pd.DataFrame:
    """Daily totals per region and payment method."""
    return (
        df.groupby(["transaction_date", "merchant_region", "payment_method"])
        .agg(
            transaction_count=("transaction_id", "count"),
            unique_users=("user_id", "nunique"),
            total_volume_usd=("amount_usd", "sum"),
            avg_transaction_usd=("amount_usd", "mean"),
            error_rate=("is_error", "mean"),
            decline_rate=("status", lambda series: series.map(is_declined).mean()),
        )
        .reset_index()
    )
