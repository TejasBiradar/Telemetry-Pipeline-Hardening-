"""Builds the frozen `BaselineStore` from a dedicated baseline-learning dataset — a
separate, clean generation run, never the same data used for tuning or evaluation
(BUILD_PLAN.md Phase 2: "three datasets, kept separate").
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import ModuleType

import pandas as pd

from datagen.generate import GenConfig, generate
from teleguard.drift.baseline import (
    BaselineStore,
    build_numeric_baseline,
    build_segment_volume_baselines,
    build_text_baseline,
)
from teleguard.evaluate.pipeline_runner import write_single_batch

# Which checkpoint/field pairs need a baseline, and which column segments them — kept in
# step with pipelines/web_analytics/contracts.yaml by hand (the two are read independently;
# a mismatch here just means a check reports "no baseline yet" rather than crashing).
NUMERIC_FIELDS = [("after_clean", "duration_s", "client_version")]
TEXT_FIELDS = [("after_ingest", "error_message", "client_version")]
SEGMENT_VOLUME_CHECKPOINTS = [("after_clean", "client_version")]


def build_baseline_store(legacy: ModuleType, seed: int = 999, n_batches: int = 20,
                         events_per_batch: int = 600) -> BaselineStore:
    cfg = GenConfig(seed=seed, n_batches=n_batches, events_per_batch=events_per_batch)
    after_ingest: list[pd.DataFrame] = []
    after_clean: list[pd.DataFrame] = []

    with tempfile.TemporaryDirectory() as tmp:
        for i, events in enumerate(generate(cfg), start=1):
            batch_dir = Path(tmp) / f"b{i:04d}"
            write_single_batch(events, batch_dir)
            ingested = legacy.ingest(batch_dir)
            after_ingest.append(ingested)
            after_clean.append(legacy.clean(ingested))

    store = BaselineStore()
    for checkpoint, field_name, segment_col in NUMERIC_FIELDS:
        pooled = pd.concat(after_clean if checkpoint == "after_clean" else after_ingest,
                           ignore_index=True)
        for segment, part in pooled.groupby(segment_col, dropna=False):
            store.set_numeric(checkpoint, field_name, str(segment),
                              build_numeric_baseline(part[field_name]))

    for checkpoint, field_name, segment_col in TEXT_FIELDS:
        pooled = pd.concat(after_clean if checkpoint == "after_clean" else after_ingest,
                           ignore_index=True)
        for segment, part in pooled.groupby(segment_col, dropna=False):
            store.set_text(checkpoint, field_name, str(segment),
                          build_text_baseline(part[field_name]))

    for checkpoint, segment_col in SEGMENT_VOLUME_CHECKPOINTS:
        per_batch = after_clean if checkpoint == "after_clean" else after_ingest
        for segment, baseline in build_segment_volume_baselines(per_batch, segment_col).items():
            store.set_segment_volume(checkpoint, segment, baseline)

    return store
