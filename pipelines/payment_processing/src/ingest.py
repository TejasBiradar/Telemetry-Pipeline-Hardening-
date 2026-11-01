"""Read payment JSONL batches into one table."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def ingest(data_dir: Path) -> pd.DataFrame:
    """Read payment JSONL into a flat table."""
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
