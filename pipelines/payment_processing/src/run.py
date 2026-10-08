"""Payment processing pipeline: clean → enrich → reconcile.

Process: ingest → clean → enrich → reconcile.
Reads JSONL payment batches (one object per line) — distinct schema from web_analytics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def ingest(data_dir: Path) -> pd.DataFrame:
    """Stage 1: read payment JSONL into a flat table."""
    rows: list[dict[str, object]] = []
    for batch_file in sorted(data_dir.glob("batch_*.jsonl")):
        batch_id = batch_file.stem
        for line in batch_file.read_text().strip().split("\n"):
            if not line:
                continue
            record = json.loads(line)
            rows.append(
                {
                    "batch_id": batch_id,
                    "transaction_id": record.get("transaction_id"),
                    "event_ts": record.get("event_ts"),
                    "merchant_id": record.get("merchant_id"),
                    "user_id": record.get("user_id"),
                    "amount_cents": record.get("amount_cents"),
                    "currency": record.get("currency"),
                    "payment_method": record.get("payment_method"),
                    "status": record.get("status"),
                    "error_message": record.get("error_message"),
                }
            )
    return pd.DataFrame(rows)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 2: dedupe, drop null users, convert cents → USD, flag errors."""
    df = df.drop_duplicates(subset=["transaction_id"], keep="first")
    df = df[df["user_id"].notna()].copy()
    df = df[(df["amount_cents"] > 0) & (df["amount_cents"] < 99_999_999)].copy()
    df["amount_usd"] = df["amount_cents"] / 100.0
    df["is_error"] = df["error_message"].notna() & df["error_message"].str.contains(
        "error", case=False, na=False
    )
    # Status vocabulary the reconciler assumes.
    allowed = {"settled", "declined", "pending", "refunded"}
    df = df[df["status"].isin(allowed)].copy()
    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 3: derive merchant region and transaction date."""
    df = df.copy()
    df["transaction_date"] = pd.to_datetime(df["event_ts"]).dt.date

    def region(merchant_id: object) -> str:
        mid = str(merchant_id)
        if mid.startswith("MER_US"):
            return "North America"
        if mid.startswith("MER_EU"):
            return "Europe"
        if mid.startswith("MER_APAC"):
            return "Asia Pacific"
        return "Other"

    df["merchant_region"] = df["merchant_id"].map(region)
    return df


def reconcile(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 4: daily totals per region and payment method."""
    return (
        df.groupby(["transaction_date", "merchant_region", "payment_method"])
        .agg(
            transaction_count=("transaction_id", "count"),
            unique_users=("user_id", "nunique"),
            total_volume_usd=("amount_usd", "sum"),
            avg_transaction_usd=("amount_usd", "mean"),
            error_rate=("is_error", "mean"),
            decline_rate=("status", lambda s: (s == "declined").mean()),
        )
        .reset_index()
    )


def run(data_dir: Path) -> pd.DataFrame:
    """Full pipeline: ingest → clean → enrich → reconcile."""
    df = ingest(data_dir)
    df = clean(df)
    df = enrich(df)
    return reconcile(df)
