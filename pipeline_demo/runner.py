"""Run a chosen reference pipeline and name the MinIO objects it writes.

The pipeline container owns this. Detection never starts the job; it only reads
the files this runner uploads under ``{prefix}/{stage}/``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pandas as pd

from pipeline_demo.catalog import pipeline_by_id, source_dir
from pipeline_demo.faults import VERSIONS, apply_fault

# Backward-compatible default for older tests / imports.
STAGES = ("ingest", "filter_sessions", "aggregate")

_METHODS: tuple[str, ...] = ("card", "wallet", "bank")
_STATUSES: tuple[str, ...] = ("settled", "declined", "pending", "refunded")
_MERCHANTS: tuple[str, ...] = ("MER_US_1", "MER_EU_2", "MER_APAC_3", "MER_US_4")


def build_events(pipeline_id: str = "user_behavior", n: int = 40) -> list[dict[str, object]]:
    """Synthetic records shaped for the selected pipeline's ingest stage."""
    if pipeline_id == "payment_processing":
        return _build_payment_events(n)
    if pipeline_id in {"user_behavior", "web_analytics"}:
        return _build_telemetry_events(n, for_web=pipeline_id == "web_analytics")
    raise ValueError(f"no event builder for pipeline {pipeline_id!r}")


def frames_from_events(
    events: list[dict[str, object]],
    *,
    fault: str = "clean",
    pipeline_id: str = "user_behavior",
) -> dict[str, pd.DataFrame]:
    """Apply one fault, run the pipeline stages, return one frame per stage."""
    spec = pipeline_by_id(pipeline_id)
    module = _load_run_module(pipeline_id)
    faulty = apply_fault(events, fault, pipeline_id=pipeline_id)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "batch_001.jsonl"
        path.write_text("".join(json.dumps(event) + "\n" for event in faulty))
        current = module.ingest(Path(tmp))
    frames: dict[str, pd.DataFrame] = {spec.stages[0]: current}
    for stage in spec.stages[1:]:
        fn = getattr(module, stage)
        current = fn(current) if not current.empty else pd.DataFrame()
        frames[stage] = current
    return frames


def object_key(prefix: str, stage: str, run_id: str) -> str:
    """Fixed layout: ``{prefix}/{stage}/{run_id}.csv``."""
    base = prefix.strip().strip("/")
    name = f"{run_id}.csv"
    if base:
        return f"{base}/{stage}/{name}"
    return f"{stage}/{name}"


def _build_telemetry_events(n: int, *, for_web: bool) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for i in range(n):
        payload: dict[str, object] = {
            "duration_ms": 1000 + i,
            "action": "page_view",
        }
        if for_web:
            payload["page"] = f"/page/{i % 5}"
            payload["error_message"] = None
        events.append(
            {
                "event_id": f"e{i}",
                "user_id": f"u{i % 8}",
                "session_id": f"s{i}" if not for_web else f"session_{(i % 5) + 1:03d}",
                "platform": "web" if i % 2 == 0 else "ios",
                "client_version": VERSIONS[i % len(VERSIONS)],
                "timestamp": 1_700_000_000_000 + i * 1000,
                "payload": payload,
            }
        )
    return events


def _build_payment_events(n: int) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for i in range(n):
        events.append(
            {
                "transaction_id": f"txn{i}",
                "event_ts": f"2024-01-{(i % 28) + 1:02d}T12:00:00Z",
                "merchant_id": _MERCHANTS[i % len(_MERCHANTS)],
                "user_id": f"u{i % 8}",
                "amount_cents": 1000 + (i * 37) % 50_000,
                "currency": "USD",
                "payment_method": _METHODS[i % len(_METHODS)],
                "status": _STATUSES[i % len(_STATUSES)],
                "error_message": None if i % 7 else "timeout error",
            }
        )
    return events


def _load_run_module(pipeline_id: str) -> ModuleType:
    """Load ``run.py`` for ``pipeline_id`` without clobbering other pipelines' modules."""
    root = source_dir(pipeline_id)
    module_name = f"pipeline_demo_run_{pipeline_id}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    path = root / "run.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load pipeline module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    # Reason: pipeline run.py may import sibling modules from its own folder.
    root_str = str(root)
    inserted = root_str not in sys.path
    if inserted:
        sys.path.insert(0, root_str)
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            sys.path.remove(root_str)
    return module
