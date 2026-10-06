"""Web analytics pipeline (Python/pandas-style, for demo). Process: ingest → clean → enrich → aggregate."""

from pathlib import Path

import pandas as pd


def ingest(data_dir: Path) -> pd.DataFrame:
    """Stage 1: read JSONL event files, unpack payload, add batch_id."""
    events = []

    for batch_file in sorted(data_dir.glob("batch_*.jsonl")):
        batch_id = batch_file.stem

        for line in batch_file.read_text().strip().split("\n"):
            if not line:
                continue

            import json
            record = json.loads(line)

            # Unpack nested payload
            payload = record.get("payload", {})
            events.append({
                "batch_id": batch_id,
                "event_id": record.get("event_id"),
                "event_ts": record.get("timestamp"),
                "user_id": record.get("user_id"),
                "session_id": record.get("session_id"),
                "platform": record.get("platform"),
                "client_version": record.get("client_version"),
                "page": payload.get("page"),
                "action": payload.get("action"),
                "duration_ms": payload.get("duration_ms"),
                "error_message": payload.get("error_message"),
            })

    df = pd.DataFrame(events)
    df["event_ts"] = pd.to_datetime(df["event_ts"], unit="ms")

    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 2: dedupe, filter nulls, convert units, flag errors."""
    # Remove duplicates
    df = df.drop_duplicates(subset=["event_id"], keep="first")

    # Filter required fields
    df = df[df["user_id"].notna()].copy()

    # Convert duration from ms to seconds
    df["duration_s"] = df["duration_ms"] / 1000.0

    # Filter unrealistic durations (> 5 minutes)
    df = df[df["duration_s"] < 300].copy()

    # Flag errors and timeouts
    df["is_error"] = df["error_message"].notna()
    df["is_timeout"] = df["error_message"].str.contains("timeout", case=False, na=False)

    # Extract major version
    df["major_version"] = df["client_version"].str.split(".").str[0]

    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 3: map countries (simulated), extract date."""
    # Simulate country mapping from session (would normally be from a lookup)
    country_map = {
        "session_001": "US",
        "session_002": "GB",
        "session_003": "DE",
        "session_004": "IN",
        "session_005": "SG",
    }

    df["country"] = df["session_id"].map(country_map).fillna("Other")

    # Extract date
    df["date"] = df["event_ts"].dt.date

    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 4: daily metrics per date/platform/country."""
    # Filter to specific actions (e.g., page views)
    page_views = df[df["action"] == "page_view"].copy()

    metrics = page_views.groupby(["date", "platform", "country"]).agg(
        events=("event_id", "count"),
        active_users=("user_id", "nunique"),
        error_rate=("is_error", "mean"),
        timeout_rate=("is_timeout", "mean"),
        avg_duration_s=("duration_s", "mean"),
        p95_duration_s=("duration_s", lambda x: x.quantile(0.95)),
    ).reset_index()

    return metrics


def run(data_dir: Path) -> pd.DataFrame:
    """Full pipeline: ingest → clean → enrich → aggregate."""
    df = ingest(data_dir)
    df = clean(df)
    df = enrich(df)
    df = aggregate(df)

    return df
