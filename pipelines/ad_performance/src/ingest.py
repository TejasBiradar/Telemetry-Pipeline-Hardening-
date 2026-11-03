"""Load raw daily campaign delivery rows from JSONL batches."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def ingest(data_dir: Path) -> pd.DataFrame:
    """Stage 1: read media delivery events into a flat table."""
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
                    "row_id": record.get("row_id"),
                    "event_date": record.get("event_date"),
                    "campaign_id": record.get("campaign_id"),
                    "channel": record.get("channel"),
                    "impressions": record.get("impressions"),
                    "clicks": record.get("clicks"),
                    "spend_usd": record.get("spend_usd"),
                    "conversions": record.get("conversions"),
                }
            )
    return pd.DataFrame(rows)
