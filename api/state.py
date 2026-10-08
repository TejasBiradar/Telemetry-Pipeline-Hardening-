"""Everything the API serves is built once, here, rather than per request.

Pipelines are discovered under ``pipelines/``. Each code graph is generated on the fly
from source analysis. Baselines and fault scenarios are chosen per active pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from teleguard.contracts.model import Contract
from teleguard.drift.baseline import BaselineStore
from teleguard.evaluate.baselines import build_baseline_store
from teleguard.evaluate.engine import EvaluationReport
from teleguard.inject.scenarios import FaultScenario, scenarios_for_pipeline
from teleguard.pipeline_loader import build_registry
from teleguard.pipeline_registry import PipelineMetadata, PipelineRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINES_ROOT = REPO_ROOT / "pipelines"


@dataclass
class AppState:
    """Multi-pipeline application state."""

    registry: PipelineRegistry
    evaluation_cache: dict[str, list[EvaluationReport]] = field(default_factory=dict)
    _scenarios_cache: dict[str, list[FaultScenario]] = field(default_factory=dict)

    def active_pipeline(self) -> PipelineMetadata | None:
        return self.registry.active()

    def legacy_module(self) -> ModuleType:
        active = self.active_pipeline()
        module = getattr(active, "_legacy_module", None) if active else None
        if isinstance(module, ModuleType):
            return module
        raise RuntimeError("No runnable module for active pipeline")

    def stages(self) -> list[str]:
        active = self.active_pipeline()
        if active is None:
            return []
        return active.stages()

    def scenarios(self) -> list[FaultScenario]:
        active = self.active_pipeline()
        if active is None:
            return []
        if active.id not in self._scenarios_cache:
            self._scenarios_cache[active.id] = scenarios_for_pipeline(active.id)
        return self._scenarios_cache[active.id]

    def baselines(self) -> BaselineStore:
        active = self.active_pipeline()
        if active is None:
            raise RuntimeError("No active pipeline")
        cached = getattr(active, "_baselines", None)
        if cached is not None:
            return cached  # type: ignore[no-any-return]
        module = getattr(active, "_legacy_module", None)
        if module is None:
            raise RuntimeError("No runnable module for active pipeline")
        try:
            store = build_baseline_store(
                module, n_batches=15, events_per_batch=3000, pipeline_id=active.id
            )
        except (KeyError, AttributeError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Baseline build failed for pipeline '{active.id}': {exc}"
            ) from exc
        active._baselines = store  # type: ignore[attr-defined]
        return store

    def contract(self) -> Contract:
        active = self.active_pipeline()
        if active and active.contract:
            return active.contract
        raise RuntimeError("No contract for active pipeline")


def build_state(
    pipelines_root: Path = PIPELINES_ROOT,
    *,
    active_id: str | None = None,
) -> AppState:
    registry = build_registry(pipelines_root, active_id=active_id)
    return AppState(registry=registry)
