"""The API: code graph, guarantees, fault scenarios, and evaluation results.

    uvicorn api.main:app --reload

Startup builds the baseline store (~15-20s); the full evaluation report is computed lazily
on first request and cached after that (~100s the first time, instant afterwards). A single
scenario run (`POST /scenarios/{name}/run`) is fast (a few seconds) since it reuses the
cached baseline store — that's the endpoint a live demo button should call.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    AlertOut,
    BatchSummaryOut,
    EvaluationSummaryOut,
    GuaranteeDecisionIn,
    GuaranteeOut,
    LineageStepOut,
    ScenarioInfo,
    ScenarioResultOut,
)
from api.state import AppState, build_state
from datagen.generate import GenConfig
from teleguard.evaluate.comparison_systems import b0_no_checks, b1_naive_schema_only, ours
from teleguard.evaluate.engine import EvaluationReport, evaluate, run_scenario, score_scenario
from teleguard.inject.scenarios import default_scenarios
from teleguard.models import CheckResult, Status

N_BATCHES = 10
EVENTS_PER_BATCH = 3000

_state: AppState | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _state
    _state = build_state()
    yield
    _state = None


app = FastAPI(title="Driftline API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # the React dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


def _state_or_503() -> AppState:
    if _state is None:
        raise HTTPException(503, "still starting up")
    return _state


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok" if _state is not None else "starting"}


@app.get("/pipelines")
def list_pipelines() -> dict[str, object]:
    """List all available pipelines and the active one."""
    state = _state_or_503()
    return state.registry.to_json()


@app.put("/pipelines/{pipeline_id}/select")
def select_pipeline(pipeline_id: str) -> dict[str, object]:
    """Switch to a different pipeline."""
    state = _state_or_503()
    if not state.registry.select(pipeline_id):
        raise HTTPException(404, f"Pipeline '{pipeline_id}' not found")
    return {"status": "ok", "active": pipeline_id}


@app.get("/pipeline/graph")
def get_graph() -> dict[str, object]:
    """Get code graph for the active pipeline."""
    state = _state_or_503()
    active = state.active_pipeline()
    if not active:
        raise HTTPException(503, "No active pipeline")
    return active.graph()  # type: ignore


@app.get("/pipeline/guarantees", response_model=list[GuaranteeOut])
def get_guarantees() -> list[GuaranteeOut]:
    """Get findings (guarantees) for the active pipeline."""
    state = _state_or_503()
    active = state.active_pipeline()
    if not active:
        raise HTTPException(503, "No active pipeline")

    out = []
    for finding in active.findings():
        decision = active.decisions.get(finding["id"], {})
        out.append(GuaranteeOut(
            id=finding["id"], kind=finding["kind"], field=finding.get("field"),
            message=finding["message"], file=finding["evidence"]["file"],
            line=finding["evidence"]["line"], status=decision.get("status", "pending"),
        ))
    return out


@app.post("/pipeline/guarantees/{guarantee_id}/decision", response_model=GuaranteeOut)
def set_guarantee_decision(guarantee_id: str, decision: GuaranteeDecisionIn) -> GuaranteeOut:
    """Confirm or reject a finding."""
    state = _state_or_503()
    active = state.active_pipeline()
    if not active:
        raise HTTPException(503, "No active pipeline")

    # Find the finding
    finding = next((f for f in active.findings() if f["id"] == guarantee_id), None)
    if finding is None:
        raise HTTPException(404, f"no such guarantee: {guarantee_id}")
    # Validate status
    if decision.status not in ("confirmed", "rejected"):
        raise HTTPException(400, f"invalid status: {decision.status}")
    # Save decision
    active.decisions[guarantee_id] = {"status": decision.status}
    _save_decisions(state)
    # Return updated guarantee
    return GuaranteeOut(
        id=finding["id"], kind=finding["kind"], field=finding.get("field"),
        message=finding["message"], file=finding["evidence"]["file"],
        line=finding["evidence"]["line"], status=decision.status,
    )


def _save_decisions(state: AppState) -> None:
    """Save decisions to disk."""
    active = state.active_pipeline()
    if not active:
        return
    decisions_path = active.source_root / "review" / "decisions.json"
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    decisions_path.write_text(json.dumps(active.decisions, indent=2))


@app.get("/scenarios", response_model=list[ScenarioInfo])
def list_scenarios() -> list[ScenarioInfo]:
    """List fault scenarios available for the active pipeline."""
    state = _state_or_503()
    # Load scenarios lazily (using web_analytics scenarios for now)
    if not hasattr(state, "_scenarios"):
        state._scenarios = default_scenarios(onset_batch=4)  # type: ignore
    return [ScenarioInfo(name=s.name, fault_type=s.fault_type.value)
           for s in state._scenarios]  # type: ignore


@app.post("/scenarios/{name}/run", response_model=ScenarioResultOut)
def run_one_scenario(name: str, system: str = "ours") -> ScenarioResultOut:
    """Run one scenario through the active pipeline.

    `system` selects what protects the pipeline:
    - "none": the plain legacy pipeline, no checks (B0). Faulty data flows through and
      the pipeline succeeds — nothing is caught. This is the "before" demo.
    - "ours": the legacy pipeline with our checks attached. Faults are caught.
    """
    state = _state_or_503()
    if not hasattr(state, "_scenarios"):
        state._scenarios = default_scenarios(onset_batch=4)  # type: ignore

    scenario = next((s for s in state._scenarios if s.name == name), None)  # type: ignore
    if scenario is None:
        raise HTTPException(404, f"no such scenario: {name}")
    if system not in ("none", "ours"):
        raise HTTPException(400, f"invalid system: {system} (use 'none' or 'ours')")

    legacy = state.legacy_module()
    contract = state.contract()
    baselines = state.baselines()

    checks_for = b0_no_checks() if system == "none" else ours(contract, baselines)
    cfg = GenConfig(seed=777, n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH)
    run = run_scenario(legacy, contract, checks_for, scenario, cfg)
    score = score_scenario(run)
    alerts = [
        AlertOut(alert_id=a.alert_id, severity=a.severity, segment=a.segment,
                root_field=a.root_field, message=a.message, affected_outputs=a.affected_outputs,
                lineage=[LineageStepOut(node_id=step.node_id, node_type=step.node_type,
                                        label=step.label) for step in a.lineage],
                first_batch=run.alert_first_batch.get(a.alert_id))
        for a in run.alerts.values()
    ]
    batches = [_summarise_batch(i, results, i in run.blocked_batches)
               for i, results in enumerate(run.results_by_batch, start=1)]
    return ScenarioResultOut(
        scenario=name, fault_type=score.fault_type.value, detected=score.detected,
        lag_batches=score.lag_batches, crashed_at_batch=score.crashed_at_batch,
        true_positive_alerts=score.true_positive_alerts,
        false_positive_alerts=score.false_positive_alerts,
        onset_batch=run.injection.onset_batch, alerts=alerts, batches=batches,
    )


def _summarise_batch(batch: int, results: list[CheckResult], blocked: bool) -> BatchSummaryOut:
    failing = [r for r in results if r.status == Status.FAIL]
    return BatchSummaryOut(
        batch=batch,
        passed=sum(r.status == Status.PASS for r in results),
        warned=sum(r.status == Status.WARN for r in results),
        failed=len(failing),
        blocked=blocked,
        failing_checks=sorted({r.check for r in failing}),
    )


@app.get("/evaluation", response_model=list[EvaluationSummaryOut])
def get_evaluation() -> list[EvaluationSummaryOut]:
    """Get evaluation results for the active pipeline."""
    state = _state_or_503()
    active = state.active_pipeline()
    if not active:
        raise HTTPException(503, "No active pipeline")

    if active.id not in state.evaluation_cache:
        state.evaluation_cache[active.id] = _run_full_evaluation(state)
    return [_to_summary(r) for r in state.evaluation_cache[active.id]]


@app.post("/evaluation/refresh", response_model=list[EvaluationSummaryOut])
def refresh_evaluation() -> list[EvaluationSummaryOut]:
    """Refresh evaluation results for the active pipeline."""
    state = _state_or_503()
    active = state.active_pipeline()
    if not active:
        raise HTTPException(503, "No active pipeline")

    state.evaluation_cache[active.id] = _run_full_evaluation(state)
    return [_to_summary(r) for r in state.evaluation_cache[active.id]]


def _run_full_evaluation(state: AppState) -> list[EvaluationReport]:
    """Run full evaluation (B0, B1, ours) for the active pipeline."""
    if not hasattr(state, "_scenarios"):
        state._scenarios = default_scenarios(onset_batch=4)  # type: ignore

    legacy = state.legacy_module()
    contract = state.contract()
    baselines = state.baselines()
    scenarios = state._scenarios  # type: ignore

    return [
        evaluate("B0", legacy, contract, b0_no_checks(), scenarios,
                n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH),
        evaluate("B1", legacy, contract, b1_naive_schema_only(), scenarios,
                n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH),
        evaluate("ours", legacy, contract, ours(contract, baselines),
                scenarios, n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH),
    ]


def _to_summary(report: EvaluationReport) -> EvaluationSummaryOut:
    return EvaluationSummaryOut(system=report.system_name, precision=report.precision,
                                recall=report.recall, mean_lag_batches=report.mean_lag_batches,
                                detection_matrix=report.detection_matrix())
