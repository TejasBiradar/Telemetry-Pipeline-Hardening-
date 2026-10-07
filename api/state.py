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

    # Add demo pipelines for testing (without full setup)
    # These show up in the selector but load web_analytics data under the hood
    user_behavior = PipelineMetadata(
        id="user_behavior",
        name="user_behavior_analytics",
        description="User session and engagement tracking pipeline",
        source_root=pipeline_dir,
        adapter_name="python_pandas",
        entry_point="run.run",
        contract=web_analytics.contract,  # Reuse contract for demo
        analysis=web_analytics.analysis,  # Reuse analysis for demo
        findings_json=web_analytics.findings_json,
        decisions=web_analytics.decisions,
        status="ready",
    )
    user_behavior._legacy_module = web_analytics._legacy_module  # type: ignore
    user_behavior._baselines = web_analytics._baselines  # type: ignore
    registry.add(user_behavior)

    payment_processing = PipelineMetadata(
        id="payment_processing",
        name="payment_processing",
        description="Payment transaction and reconciliation pipeline",
        source_root=pipeline_dir,
        adapter_name="python_pandas",
        entry_point="run.run",
        contract=web_analytics.contract,  # Reuse contract for demo
        analysis=web_analytics.analysis,  # Reuse analysis for demo
        findings_json=web_analytics.findings_json,
        decisions=web_analytics.decisions,
        status="ready",
    )
    payment_processing._legacy_module = web_analytics._legacy_module  # type: ignore
    payment_processing._baselines = web_analytics._baselines  # type: ignore
    registry.add(payment_processing)

    return AppState(registry=registry)


def _load_pipeline(pipeline_id: str, pipeline_dir: Path) -> PipelineMetadata:
    """Load a single pipeline from disk.

    Reads pre-existing graph.json and contracts.yaml (for web_analytics demo).
    For uploaded pipelines, graph is generated dynamically.
    """
    from teleguard.adapters.base import AnalysisResult
    from teleguard.codegraph.model import CodeGraph, Node, Edge, NodeType, EdgeType, Origin, Evidence

    legacy = load_module(pipeline_dir / "legacy" / "run.py")
    contract = load_contract(pipeline_dir / "contracts.yaml")
    baselines = build_baseline_store(legacy, n_batches=15, events_per_batch=3000)

    # Load graph and findings from disk (web_analytics only)
    graph_json = json.loads((pipeline_dir / "codegraph" / "graph.json").read_text())
    findings_json = json.loads((pipeline_dir / "codegraph" / "findings.json").read_text())
    decisions_path = pipeline_dir / "review" / "decisions.json"
    decisions = json.loads(decisions_path.read_text()) if decisions_path.exists() else {}

    # Reconstruct CodeGraph from JSON
    graph = CodeGraph()
    for node_data in graph_json.get("nodes", []):
        node = Node(
            id=node_data["id"],
            type=NodeType(node_data["type"]),
            label=node_data["label"],
            attrs=node_data.get("attrs", {}),
            origin=Origin(node_data.get("origin", "static")),
        )
        graph.add_node(node)

    for edge_data in graph_json.get("edges", []):
        evidence_data = edge_data.get("evidence")
        evidence = Evidence(
            file=evidence_data["file"],
            line=evidence_data["line"],
            snippet=evidence_data.get("snippet", ""),
        ) if evidence_data else None
        edge = Edge(
            source=edge_data["source"],
            target=edge_data["target"],
            type=EdgeType(edge_data["type"]),
            evidence=evidence,
            attrs=edge_data.get("attrs", {}),
            origin=Origin(edge_data.get("origin", "static")),
        )
        graph.add_edge(edge)

    # Create AnalysisResult with the graph
    analysis = AnalysisResult(
        graph=graph,
        findings=[],  # Will be loaded separately
        stages=[s for s in contract.checkpoints[0].checkpoint.replace("after_", "").split("_") if s],
        checkpoints=[cp.checkpoint for cp in contract.checkpoints],
    )

    # Create metadata
    metadata = PipelineMetadata(
        id=pipeline_id,
        name=contract.pipeline,
        source_root=pipeline_dir,
        adapter_name="python_pandas",
        entry_point="run.run",
        contract=contract,
        analysis=analysis,  # Now has the full graph!
        findings_json=findings_json,
        decisions=decisions,
        status="ready",
    )

    # Store module and baselines for later use (not in AnalysisResult, so we stash them)
    metadata._legacy_module = legacy  # type: ignore
    metadata._baselines = baselines  # type: ignore

    return metadata
