"""Builds the frozen `BaselineStore` from a dedicated baseline-learning dataset — a
separate, clean generation run, never the same data used for tuning or evaluation
(BUILD_PLAN.md Phase 2: "three datasets, kept separate").
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd

from datagen.catalog import generate_for_pipeline
from datagen.generate import GenConfig
from teleguard.drift.baseline import (
    BaselineStore,
    build_numeric_baseline,
    build_segment_volume_baselines,
    build_text_baseline,
)
from teleguard.evaluate.pipeline_runner import write_single_batch

GenerateFn = Callable[[GenConfig], list[list[dict[str, Any]]]]


@dataclass(frozen=True)
class BaselinePlan:
    """Which mid-stage + fields to profile for one pipeline."""

    mid_stage: str  # function after ingest (clean / filter_sessions / …)
    numeric_fields: tuple[tuple[str, str, str], ...]  # (checkpoint, field, segment_col)
    text_fields: tuple[tuple[str, str, str], ...]
    segment_volume: tuple[tuple[str, str], ...]  # (checkpoint, segment_col)


_PLANS: dict[str, BaselinePlan] = {
    "web_analytics": BaselinePlan(
        mid_stage="clean",
        numeric_fields=(("after_clean", "duration_s", "client_version"),),
        text_fields=(("after_ingest", "error_message", "client_version"),),
        segment_volume=(("after_clean", "client_version"),),
    ),
    "user_behavior": BaselinePlan(
        mid_stage="filter_sessions",
        numeric_fields=(("after_filter_sessions", "session_duration_s", "client_version"),),
        text_fields=(),
        segment_volume=(("after_filter_sessions", "client_version"),),
    ),
    "payment_processing": BaselinePlan(
        mid_stage="clean",
        numeric_fields=(("after_clean", "amount_usd", "payment_method"),),
        text_fields=(("after_ingest", "error_message", "payment_method"),),
        segment_volume=(("after_clean", "payment_method"),),
    ),
}


def plan_for(pipeline_id: str) -> BaselinePlan:
    return _PLANS.get(pipeline_id, _PLANS["web_analytics"])


def build_baseline_store(
    legacy: ModuleType,
    seed: int = 999,
    n_batches: int = 20,
    events_per_batch: int = 600,
    *,
    pipeline_id: str = "web_analytics",
    generate_batches: GenerateFn | None = None,
) -> BaselineStore:
    plan = plan_for(pipeline_id)
    mid_fn = getattr(legacy, plan.mid_stage, None)
    if not callable(getattr(legacy, "ingest", None)) or not callable(mid_fn):
        raise TypeError(
            f"Pipeline '{pipeline_id}' needs ingest + {plan.mid_stage} for baselines"
        )

    gen = generate_batches or generate_for_pipeline(pipeline_id)
    cfg = GenConfig(seed=seed, n_batches=n_batches, events_per_batch=events_per_batch)
    after_ingest: list[pd.DataFrame] = []
    after_mid: list[pd.DataFrame] = []

    with tempfile.TemporaryDirectory() as tmp:
        for i, events in enumerate(gen(cfg), start=1):
            batch_dir = Path(tmp) / f"b{i:04d}"
            write_single_batch(events, batch_dir)
            ingested = legacy.ingest(batch_dir)
            after_ingest.append(ingested)
            after_mid.append(mid_fn(ingested))

    store = BaselineStore()
    frames = {"after_ingest": after_ingest, f"after_{plan.mid_stage}": after_mid}

    for checkpoint, field_name, segment_col in plan.numeric_fields:
        pooled = pd.concat(frames[checkpoint], ignore_index=True)
        for segment, part in pooled.groupby(segment_col, dropna=False):
            store.set_numeric(
                checkpoint,
                field_name,
                str(segment),
                build_numeric_baseline(part[field_name]),
            )

    for checkpoint, field_name, segment_col in plan.text_fields:
        pooled = pd.concat(frames[checkpoint], ignore_index=True)
        if field_name not in pooled.columns:
            continue
        for segment, part in pooled.groupby(segment_col, dropna=False):
            store.set_text(
                checkpoint,
                field_name,
                str(segment),
                build_text_baseline(part[field_name]),
            )

    for checkpoint, segment_col in plan.segment_volume:
        per_batch = frames[checkpoint]
        for segment, baseline in build_segment_volume_baselines(per_batch, segment_col).items():
            store.set_segment_volume(checkpoint, segment, baseline)

    return store


# Kept for older imports / tests that expected these constants.
NUMERIC_FIELDS = [("after_clean", "duration_s", "client_version")]
TEXT_FIELDS = [("after_ingest", "error_message", "client_version")]
SEGMENT_VOLUME_CHECKPOINTS = [("after_clean", "client_version")]
