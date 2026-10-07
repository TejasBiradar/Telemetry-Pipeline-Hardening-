"""Everything the API serves is built once, here, rather than per request.

The baseline store needs ~15 clean batches run through the real pipeline to build
(~15-20s); the full evaluation report needs all 8 scenarios run against all 3 systems
(~100s). Both are computed once and cached, not on every GET.

Multi-pipeline support: registry holds all pipelines, one is active. Graphs are
generated dynamically from code analysis, not loaded from JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from teleguard.contracts.model import Contract, load_contract
from teleguard.drift.baseline import BaselineStore
from teleguard.evaluate.baselines import build_baseline_store
from teleguard.evaluate.engine import EvaluationReport
from teleguard.inject.scenarios import FaultScenario, default_scenarios
from teleguard.pipeline_registry import PipelineMetadata, PipelineRegistry
from teleguard.tracer import load_module

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = REPO_ROOT / "pipelines" / "web_analytics"


@dataclass
class AppState:
    """Multi-pipeline application state."""

    registry: PipelineRegistry
    # Lazily filled on first GET /evaluation, not at startup, so the server comes up fast.
    evaluation_cache: dict[str, list[EvaluationReport]] = field(default_factory=dict)

    def active_pipeline(self) -> PipelineMetadata | None:
        """Get the currently active pipeline."""
        return self.registry.active()

    def legacy_module(self) -> ModuleType:
        """Get the active pipeline's Python module (for running it)."""
        active = self.active_pipeline()
        if active and hasattr(active, "_legacy_module"):
            return active._legacy_module  # type: ignore
        raise RuntimeError("No active pipeline loaded")

    def baselines(self) -> BaselineStore:
        """Get the active pipeline's baseline store."""
        active = self.active_pipeline()
        if active and hasattr(active, "_baselines"):
            return active._baselines  # type: ignore
        raise RuntimeError("No baselines for active pipeline")

    def contract(self) -> Contract:
        """Get the active pipeline's contract."""
        active = self.active_pipeline()
        if active and active.contract:
            return active.contract
        raise RuntimeError("No contract for active pipeline")


def build_state(pipeline_dir: Path = PIPELINE_DIR) -> AppState:
    """Build initial state with web_analytics as the default pipeline."""
    registry = PipelineRegistry()

    # Load web_analytics (the built-in demo pipeline)
    web_analytics = _load_pipeline("web_analytics", pipeline_dir)
    registry.add(web_analytics)
    registry.select("web_analytics")

    return AppState(registry=registry)


def _load_pipeline(pipeline_id: str, pipeline_dir: Path) -> PipelineMetadata:
    """Load a single pipeline from disk.

    Reads pre-existing graph.json and contracts.yaml (for web_analytics demo).
    For uploaded pipelines, graph is generated dynamically.
    """
    legacy = load_module(pipeline_dir / "legacy" / "run.py")
    contract = load_contract(pipeline_dir / "contracts.yaml")
    baselines = build_baseline_store(legacy, n_batches=15, events_per_batch=3000)

    # Load graph and findings from disk (web_analytics only)
    findings_json = json.loads((pipeline_dir / "codegraph" / "findings.json").read_text())
    decisions_path = pipeline_dir / "review" / "decisions.json"
    decisions = json.loads(decisions_path.read_text()) if decisions_path.exists() else {}

    # Create metadata
    metadata = PipelineMetadata(
        id=pipeline_id,
        name=contract.pipeline,
        source_root=pipeline_dir,
        adapter_name="python_pandas",
        entry_point="run.run",
        contract=contract,
        findings_json=findings_json,
        decisions=decisions,
        status="ready",
    )

    # Store module and baselines for later use (not in AnalysisResult, so we stash them)
    metadata._legacy_module = legacy  # type: ignore
    metadata._baselines = baselines  # type: ignore

    return metadata
