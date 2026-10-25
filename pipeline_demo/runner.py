"""Run the user-behavior pipeline and name the MinIO objects it writes.

The pipeline container owns this. Detection never starts the job; it only reads
the files this runner uploads under ``{prefix}/{stage}/``.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

from pipeline_demo.faults import VERSIONS, apply_fault

STAGES = ("ingest", "filter_sessions", "aggregate")


def build_events(n: int = 40) -> list[dict[str, object]]:
    """Synthetic events in the shape ``user_behavior`` ingest expects."""
    events: list[dict[str, object]] = []
    for i in range(n):
        events.append(
            {
                "event_id": f"e{i}",
                "user_id": f"u{i % 8}",
                "session_id": f"s{i}",
                "platform": "web" if i % 2 == 0 else "ios",
                "client_version": VERSIONS[i % len(VERSIONS)],
                "timestamp": 1_700_000_000_000 + i * 1000,
                "payload": {"duration_ms": 1000 + i, "action": "page_view"},
            }
        )
    return events


def frames_from_events(events: list[dict[str, object]], *, fault: str = "clean") -> dict[str, pd.DataFrame]:
    """Run ingest → filter → aggregate after applying one demo fault to the events."""
    from run import aggregate, filter_sessions, ingest

    faulty = apply_fault(events, fault)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "batch_001.jsonl"
        path.write_text("".join(json.dumps(event) + "\n" for event in faulty))
        ingested = ingest(Path(tmp))
    filtered = filter_sessions(ingested)
    aggregated = aggregate(filtered) if not filtered.empty else pd.DataFrame()
    return {
        "ingest": ingested,
        "filter_sessions": filtered,
        "aggregate": aggregated,
    }


def object_key(prefix: str, stage: str, run_id: str) -> str:
    """Fixed layout: ``{prefix}/{stage}/{run_id}.csv``."""
    base = prefix.strip().strip("/")
    name = f"{run_id}.csv"
    if base:
        return f"{base}/{stage}/{name}"
    return f"{stage}/{name}"
