"""Demo pipelines the trigger UI can run into MinIO."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineSpec:
    """One reference pipeline the demo trigger can execute."""

    pipeline_id: str
    label: str
    stages: tuple[str, ...]
    prefix: str
    # Relative to PIPELINE_SRC_ROOT (Docker) or the repo pipelines/ tree (local).
    source_rel: str


PIPELINES: dict[str, PipelineSpec] = {
    "user_behavior": PipelineSpec(
        pipeline_id="user_behavior",
        label="User Behavior",
        stages=("ingest", "filter_sessions", "aggregate"),
        prefix="demo/user_behavior/outputs",
        source_rel="user_behavior",
    ),
    "payment_processing": PipelineSpec(
        pipeline_id="payment_processing",
        label="Payment Processing",
        stages=("ingest", "clean", "enrich", "reconcile"),
        prefix="demo/payment_processing/outputs",
        source_rel="payment_processing",
    ),
    "web_analytics": PipelineSpec(
        pipeline_id="web_analytics",
        label="Web Analytics",
        stages=("ingest", "clean", "enrich", "aggregate"),
        prefix="demo/web_analytics/outputs",
        source_rel="web_analytics",
    ),
}

# Repo-relative source folders when not running under Docker.
_REPO_SOURCE: dict[str, str] = {
    "user_behavior": "pipelines/user_behavior/src",
    "payment_processing": "pipelines/payment_processing/src",
    "web_analytics": "pipelines/web_analytics/legacy",
}


def list_pipelines() -> list[PipelineSpec]:
    return [PIPELINES[key] for key in ("user_behavior", "payment_processing", "web_analytics")]


def pipeline_by_id(pipeline_id: str) -> PipelineSpec:
    try:
        return PIPELINES[pipeline_id]
    except KeyError as exc:
        known = ", ".join(PIPELINES)
        raise ValueError(f"unknown pipeline {pipeline_id!r}; expected one of: {known}") from exc


def source_dir(pipeline_id: str) -> Path:
    """Directory that contains ``run.py`` for ``pipeline_id``."""
    spec = pipeline_by_id(pipeline_id)
    root_env = os.environ.get("PIPELINE_SRC_ROOT", "").strip()
    if root_env:
        path = Path(root_env) / spec.source_rel
    else:
        repo = Path(__file__).resolve().parents[1]
        path = repo / _REPO_SOURCE[pipeline_id]
    if not path.is_dir():
        raise FileNotFoundError(f"pipeline source is not a directory: {path}")
    if not (path / "run.py").is_file():
        raise FileNotFoundError(f"pipeline source missing run.py: {path}")
    return path
