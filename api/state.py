"""Everything the API serves is built once, here, rather than per request.

The baseline store needs ~15 clean batches run through the real pipeline to build
(~15-20s); the full evaluation report needs all 8 scenarios run against all 3 systems
(~100s). Both are computed once and cached, not on every GET.
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
from teleguard.tracer import load_module

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = REPO_ROOT / "pipelines" / "web_analytics"


@dataclass
class AppState:
    pipeline_name: str
    legacy: ModuleType
    contract: Contract
    baselines: BaselineStore
    scenarios: list[FaultScenario]
    graph: dict[str, Any]
    findings: list[dict[str, Any]]
    decisions: dict[str, Any]
    # Lazily filled on first GET /evaluation, not at startup, so the server comes up fast.
    evaluation_cache: list[EvaluationReport] | None = field(default=None)


def build_state(pipeline_dir: Path = PIPELINE_DIR) -> AppState:
    legacy = load_module(pipeline_dir / "legacy" / "run.py")
    contract = load_contract(pipeline_dir / "contracts.yaml")
    baselines = build_baseline_store(legacy, n_batches=15, events_per_batch=3000)
    scenarios = default_scenarios(onset_batch=4)
    graph = json.loads((pipeline_dir / "codegraph" / "graph.json").read_text())
    findings = json.loads((pipeline_dir / "codegraph" / "findings.json").read_text())
    decisions_path = pipeline_dir / "review" / "decisions.json"
    decisions = json.loads(decisions_path.read_text()) if decisions_path.exists() else {}
    return AppState(pipeline_name=contract.pipeline, legacy=legacy, contract=contract,
                    baselines=baselines, scenarios=scenarios, graph=graph, findings=findings,
                    decisions=decisions)
