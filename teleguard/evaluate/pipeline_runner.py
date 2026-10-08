"""Runs one batch through a pipeline with the guard attached between stages.

Stage order comes from static analysis (the functions ``run()`` calls). The first stage
receives the batch directory; later stages receive the previous DataFrame.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd

from teleguard.contracts.model import Contract
from teleguard.guard import BatchRejectedError, Guard
from teleguard.models import BatchContext

# Default for older callers / web_analytics evaluation tests.
STAGES = ("ingest", "clean", "enrich", "aggregate")


def write_single_batch(events: list[dict[str, Any]], batch_dir: Path, number: int = 1) -> Path:
    """Writes one batch as JSONL lines the pipeline ingest can read."""
    batch_dir.mkdir(parents=True, exist_ok=True)
    path = batch_dir / f"batch_{number:04d}.jsonl"
    path.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in events))
    return path


@dataclass
class BatchOutcome:
    batch_id: str
    blocked_at: str | None
    crashed_at: str | None
    error: str | None = None


def run_batch(
    legacy: ModuleType,
    batch_dir: Path,
    pipeline: str,
    batch_id: str,
    contract: Contract,
    guard: Guard,
    stages: list[str] | tuple[str, ...] = STAGES,
) -> BatchOutcome:
    """Run ``stages`` in order, calling ``guard.check(after_<stage>, …)`` after each."""

    def ctx_for(checkpoint: str) -> BatchContext:
        cp = contract.for_checkpoint(checkpoint)
        return BatchContext(
            pipeline=pipeline,
            batch_id=batch_id,
            segment_column=cp.segment_by if cp else None,
        )

    if not stages:
        return BatchOutcome(batch_id, blocked_at=None, crashed_at=None, error="no stages")

    stage = stages[0]
    try:
        df: pd.DataFrame | None = None
        for index, stage in enumerate(stages):
            fn = getattr(legacy, stage)
            df = fn(batch_dir) if index == 0 else fn(df)
            checkpoint = f"after_{stage}"
            df = guard.check(checkpoint, df, ctx_for(checkpoint))
    except BatchRejectedError as exc:
        return BatchOutcome(batch_id, blocked_at=exc.checkpoint, crashed_at=None)
    except Exception as exc:  # noqa: BLE001 — pipeline crash is a scored outcome
        return BatchOutcome(batch_id, blocked_at=None, crashed_at=stage, error=str(exc))
    return BatchOutcome(batch_id, blocked_at=None, crashed_at=None)
