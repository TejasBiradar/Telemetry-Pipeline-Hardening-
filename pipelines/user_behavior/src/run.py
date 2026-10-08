"""User behavior pipeline: session-based engagement tracking.

Process: ingest → filter_sessions → aggregate.
Reads the same JSONL batch format as web_analytics so a shared datagen feed can drive it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def ingest(data_dir: Path) -> pd.DataFrame:
    """Stage 1: read JSONL events into session-oriented rows."""
    sessions: list[dict[str, object]] = []
    for batch_file in sorted(data_dir.glob("batch_*.jsonl")):
        batch_id = batch_file.stem
        for line in batch_file.read_text().strip().split("\n"):
            if not line:
                continue
            record = json.loads(line)
            payload = record.get("payload", {})
            sessions.append(
                {
                    "batch_id": batch_id,
                    "event_id": record.get("event_id"),
                    "user_id": record.get("user_id"),
                    "session_id": record.get("session_id"),
                    "platform": record.get("platform"),
                    "client_version": record.get("client_version"),
                    "session_start_ms": record.get("timestamp"),
                    "duration_ms": payload.get("duration_ms"),
                    "action": payload.get("action"),
                }
            )
    df = pd.DataFrame(sessions)
    if not df.empty:
        df["session_start"] = pd.to_datetime(df["session_start_ms"], unit="ms")
    return df


def filter_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 2: drop null users, convert duration, keep page views only."""
    df = df[df["user_id"].notna()].copy()
    df["session_duration_s"] = df["duration_ms"] / 1000.0
    # Silent filter: engagement metrics only count page views.
    df = df[df["action"] == "page_view"].copy()
    df = df[df["session_duration_s"] < 3600].copy()
    df["major_version"] = df["client_version"].str.split(".").str[0]
    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 3: per-user engagement rollup."""
    metrics = (
        df.groupby("user_id")
        .agg(
            session_count=("session_id", "nunique"),
            platforms_used=("platform", "nunique"),
            avg_session_duration_s=("session_duration_s", "mean"),
            events=("event_id", "count"),
        )
        .reset_index()
    )
    metrics["engagement_score"] = (
        metrics["session_count"] * metrics["platforms_used"]
    )
    return metrics


def run(data_dir: Path) -> pd.DataFrame:
    """Full pipeline: ingest → filter_sessions → aggregate."""
    df = ingest(data_dir)
    df = filter_sessions(df)
    return aggregate(df)
