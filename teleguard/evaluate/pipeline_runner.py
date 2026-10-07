"""Runs one batch of events through the real `web_analytics` pipeline with the guard
attached between stages — an "out-of-process tap" (ARCHITECTURE.md §1): the frozen pipeline
in `pipelines/web_analytics/legacy/run.py` is never edited, only called into from here.

Specific to web_analytics's four stages for now; a pipeline-agnostic version is future work
(BUILD_PLAN.md ADR-13, still open) and not needed to produce real evaluation numbers today.
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

STAGES = ("after_ingest", "after_clean", "after_enrich", "after_aggregate")


def write_single_batch(events: list[dict[str, Any]], batch_dir: Path, number: int = 1) -> Path:
    """Writes one batch exactly as `datagen.generate.write()` would, so injected data is
    indistinguishable in format from the real generator's output."""
    batch_dir.mkdir(parents=True, exist_ok=True)
    path = batch_dir / f"batch_{number:04d}.jsonl"
    path.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in events))
    return path


@dataclass
class BatchOutcome:
    batch_id: str
    blocked_at: str | None  # checkpoint name, if a gate rejected this batch
    crashed_at: str | None  # "ingest"/"clean"/"enrich"/"aggregate", if the stage itself raised
    error: str | None = None


def run_batch(legacy: ModuleType, batch_dir: Path, pipeline: str, batch_id: str,
             contract: Contract, guard: Guard) -> BatchOutcome:
    """Runs one batch through ingest -> clean -> enrich -> aggregate, calling
    `guard.check()` after each stage. In enforce mode a failing gate raises
    `BatchRejectedError` *before* the next (possibly crash-prone) stage runs — e.g. a
    type-change fault is stopped at `after_ingest`'s schema check, not left to crash
    `clean()`'s arithmetic on a now-textual field."""

    def ctx_for(checkpoint: str) -> BatchContext:
        cp = contract.for_checkpoint(checkpoint)
        return BatchContext(pipeline=pipeline, batch_id=batch_id,
                           segment_column=cp.segment_by if cp else None)

    stage = "ingest"
    try:
        df: pd.DataFrame = legacy.ingest(batch_dir)
        df = guard.check("after_ingest", df, ctx_for("after_ingest"))
        stage = "clean"
        df = legacy.clean(df)
        df = guard.check("after_clean", df, ctx_for("after_clean"))
        stage = "enrich"
        df = legacy.enrich(df)
        df = guard.check("after_enrich", df, ctx_for("after_enrich"))
        stage = "aggregate"
        df = legacy.aggregate(df)
        guard.check("after_aggregate", df, ctx_for("after_aggregate"))
    except BatchRejectedError as exc:
        return BatchOutcome(batch_id, blocked_at=exc.checkpoint, crashed_at=None)
    except Exception as exc:  # noqa: BLE001 - the pipeline crashing on bad data is itself a result
        return BatchOutcome(batch_id, blocked_at=None, crashed_at=stage, error=str(exc))
    return BatchOutcome(batch_id, blocked_at=None, crashed_at=None)
