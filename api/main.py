"""The API: code graph, guarantees, fault scenarios, and evaluation results.

    uvicorn api.main:app --reload

Startup builds the baseline store (~15-20s); the full evaluation report is computed lazily
on first request and cached after that (~100s the first time, instant afterwards). A single
scenario run (`POST /scenarios/{name}/run`) is fast (a few seconds) since it reuses the
cached baseline store — that's the endpoint a live demo button should call.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    AlertOut,
    EvaluationSummaryOut,
    GuaranteeOut,
    ScenarioInfo,
    ScenarioResultOut,
)
from api.state import AppState, build_state
from datagen.generate import GenConfig
from teleguard.evaluate.comparison_systems import b0_no_checks, b1_naive_schema_only, ours
from teleguard.evaluate.engine import EvaluationReport, evaluate, run_scenario, score_scenario

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


@app.get("/pipeline/graph")
def get_graph() -> dict[str, object]:
    return _state_or_503().graph


@app.get("/pipeline/guarantees", response_model=list[GuaranteeOut])
def get_guarantees() -> list[GuaranteeOut]:
    state = _state_or_503()
    out = []
    for finding in state.findings:
        decision = state.decisions.get(finding["id"], {})
        out.append(GuaranteeOut(
            id=finding["id"], kind=finding["kind"], field=finding.get("field"),
            message=finding["message"], file=finding["evidence"]["file"],
            line=finding["evidence"]["line"], status=decision.get("status", "pending"),
        ))
    return out


@app.get("/scenarios", response_model=list[ScenarioInfo])
def list_scenarios() -> list[ScenarioInfo]:
    return [ScenarioInfo(name=s.name, fault_type=s.fault_type.value)
           for s in _state_or_503().scenarios]


@app.post("/scenarios/{name}/run", response_model=ScenarioResultOut)
def run_one_scenario(name: str) -> ScenarioResultOut:
    state = _state_or_503()
    scenario = next((s for s in state.scenarios if s.name == name), None)
    if scenario is None:
        raise HTTPException(404, f"no such scenario: {name}")

    cfg = GenConfig(seed=777, n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH)
    run = run_scenario(state.legacy, state.contract, ours(state.contract, state.baselines),
                       scenario, cfg)
    score = score_scenario(run)
    alerts = [
        AlertOut(alert_id=a.alert_id, severity=a.severity, segment=a.segment,
                root_field=a.root_field, message=a.message, affected_outputs=a.affected_outputs)
        for a in run.alerts.values()
    ]
    return ScenarioResultOut(
        scenario=name, fault_type=score.fault_type.value, detected=score.detected,
        lag_batches=score.lag_batches, crashed_at_batch=score.crashed_at_batch,
        true_positive_alerts=score.true_positive_alerts,
        false_positive_alerts=score.false_positive_alerts, alerts=alerts,
    )


@app.get("/evaluation", response_model=list[EvaluationSummaryOut])
def get_evaluation() -> list[EvaluationSummaryOut]:
    state = _state_or_503()
    if state.evaluation_cache is None:
        state.evaluation_cache = _run_full_evaluation(state)
    return [_to_summary(r) for r in state.evaluation_cache]


@app.post("/evaluation/refresh", response_model=list[EvaluationSummaryOut])
def refresh_evaluation() -> list[EvaluationSummaryOut]:
    state = _state_or_503()
    state.evaluation_cache = _run_full_evaluation(state)
    return [_to_summary(r) for r in state.evaluation_cache]


def _run_full_evaluation(state: AppState) -> list[EvaluationReport]:
    return [
        evaluate("B0", state.legacy, state.contract, b0_no_checks(), state.scenarios,
                n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH),
        evaluate("B1", state.legacy, state.contract, b1_naive_schema_only(), state.scenarios,
                n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH),
        evaluate("ours", state.legacy, state.contract, ours(state.contract, state.baselines),
                state.scenarios, n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH),
    ]


def _to_summary(report: EvaluationReport) -> EvaluationSummaryOut:
    return EvaluationSummaryOut(system=report.system_name, precision=report.precision,
                                recall=report.recall, mean_lag_batches=report.mean_lag_batches,
                                detection_matrix=report.detection_matrix())
