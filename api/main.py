"""The API: code graph, guarantees, fault scenarios, and evaluation results.

    uvicorn api.main:app --reload

Startup builds the baseline store (~15-20s); the full evaluation report is computed lazily
on first request and cached after that (~100s the first time, instant afterwards). A single
scenario run (`POST /scenarios/{name}/run`) is fast (a few seconds) since it reuses the
cached baseline store — that's the endpoint a live demo button should call.
"""

from __future__ import annotations

import json
import smtplib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.schemas import (
    AlertOut,
    BatchSummaryOut,
    EvaluationSummaryOut,
    GuaranteeDecisionIn,
    GuaranteeOut,
    LineageStepOut,
    OnboardIn,
    OnboardOut,
    ScenarioInfo,
    ScenarioResultOut,
)
from api.state import AppState, build_state
from datagen.catalog import generate_for_pipeline
from datagen.generate import GenConfig
from teleguard.contracts.decisions_filter import (
    contract_for_decisions,
    contract_needs_baselines,
)
from teleguard.drift.baseline import BaselineStore
from teleguard.evaluate.comparison_systems import b0_no_checks, b1_naive_schema_only, ours
from teleguard.evaluate.engine import EvaluationReport, evaluate, run_scenario, score_scenario
from teleguard.models import CheckResult, Status
from teleguard.notify.email import alert_email_body, send_mail, smtp_configured
from teleguard.notify.onboard import OnboardRecord, load_onboard, save_onboard

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


@app.get("/onboard", response_model=OnboardOut)
def get_onboard() -> OnboardOut:
    record = load_onboard()
    if record is None:
        active = _state_or_503().active_pipeline()
        return OnboardOut(
            email="",
            pipeline_id=active.id if active else "",
            source_note="",
            smtp_configured=smtp_configured(),
        )
    return OnboardOut(
        email=record.email,
        pipeline_id=record.pipeline_id,
        source_note=record.source_note,
        smtp_configured=smtp_configured(),
    )


@app.post("/onboard", response_model=OnboardOut)
def post_onboard(body: OnboardIn) -> OnboardOut:
    state = _state_or_503()
    if body.pipeline_id not in state.registry.pipelines:
        raise HTTPException(404, f"unknown pipeline: {body.pipeline_id}")
    try:
        save_onboard(
            OnboardRecord(
                email=body.email.strip(),
                pipeline_id=body.pipeline_id,
                source_note=body.source_note.strip(),
            )
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    sent: str | None = None
    err: str | None = None
    if smtp_configured():
        try:
            send_mail(
                body.email.strip(),
                f"[Driftline] onboarded {body.pipeline_id}",
                (
                    f"You are registered for alerts on pipeline '{body.pipeline_id}'.\n"
                    f"Source note: {body.source_note or '(none)'}\n\n"
                    "When a fault scenario raises alerts, they are emailed here.\n"
                ),
            )
            sent = "welcome"
        except (OSError, smtplib.SMTPException, RuntimeError, TimeoutError) as exc:
            err = f"{type(exc).__name__}: {exc}"
    record = load_onboard()
    assert record is not None
    return OnboardOut(
        email=record.email,
        pipeline_id=record.pipeline_id,
        source_note=record.source_note,
        smtp_configured=smtp_configured(),
        email_sent=sent,
        email_error=err,
    )


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
    """Get code graph and pipeline stages for the active pipeline."""
    state = _state_or_503()
    active = state.active_pipeline()
    if not active:
        raise HTTPException(503, "No active pipeline")
    graph_data = active.graph()
    # Include stages so the UI can render stage-based visualization
    graph_data["stages"] = active.stages()
    return graph_data


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


class CodegenRequest(BaseModel):
    code: str


@app.post("/pipeline/codegraph/generate")
def generate_codegraph(req: CodegenRequest) -> dict[str, object]:
    """Generate a code graph from a pipeline source string (on the fly, no cache)."""
    import tempfile
    import traceback

    from teleguard.analyze import analyze_legacy

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir) / "run.py"
            tmppath.write_text(req.code)
            analysis, _language = analyze_legacy(Path(tmpdir), entry="run.run")
            return {
                "success": True,
                "graph": analysis.graph.to_json(),
                "stages": [analysis.graph.node(s).label for s in analysis.stages],
                "findings": [f.to_json() for f in analysis.findings],
            }
    except (OSError, ValueError, KeyError, AttributeError, TypeError, SyntaxError) as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


@app.get("/scenarios", response_model=list[ScenarioInfo])
def list_scenarios() -> list[ScenarioInfo]:
    """List fault scenarios for the *active* pipeline (catalogue differs per pipeline)."""
    state = _state_or_503()
    return [
        ScenarioInfo(name=s.name, fault_type=s.fault_type.value, description=s.description)
        for s in state.scenarios()
    ]


@app.post("/scenarios/{name}/run", response_model=ScenarioResultOut)
def run_one_scenario(name: str, system: str = "ours") -> ScenarioResultOut:
    """Run one scenario through the active pipeline.

    `system` selects what protects the pipeline:
    - "none": the plain legacy pipeline, no checks (B0). Faulty data flows through and
      the pipeline succeeds — nothing is caught. This is the "before" demo.
    - "ours": enforce only checks backed by *confirmed* guarantees (rejected/pending
      findings do not run). If nothing is confirmed, this matches Checks OFF.
    """
    state = _state_or_503()
    scenarios = state.scenarios()
    scenario = next((s for s in scenarios if s.name == name), None)
    if scenario is None:
        raise HTTPException(404, f"no such scenario: {name}")
    if system not in ("none", "ours"):
        raise HTTPException(400, f"invalid system: {system} (use 'none' or 'ours')")

    try:
        legacy = state.legacy_module()
        active = state.active_pipeline()
        if active is None:
            raise RuntimeError("No active pipeline")
        base_contract = state.contract()
        if system == "none":
            contract = base_contract
            checks_for = b0_no_checks()
        else:
            contract = contract_for_decisions(
                base_contract, active.findings(), active.decisions
            )
            if not contract.checkpoints:
                checks_for = b0_no_checks()
            elif contract_needs_baselines(contract):
                checks_for = ours(contract, state.baselines())
            else:
                checks_for = ours(contract, BaselineStore())
    except (RuntimeError, AttributeError, TypeError) as exc:
        raise HTTPException(501, str(exc)) from exc

    cfg = GenConfig(seed=777, n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH)
    run = run_scenario(
        legacy,
        contract,
        checks_for,
        scenario,
        cfg,
        stages=state.stages(),
        generate_batches=generate_for_pipeline(active.id),
    )
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
    out = ScenarioResultOut(
        scenario=name, fault_type=score.fault_type.value, detected=score.detected,
        lag_batches=score.lag_batches, crashed_at_batch=score.crashed_at_batch,
        true_positive_alerts=score.true_positive_alerts,
        false_positive_alerts=score.false_positive_alerts,
        onset_batch=run.injection.onset_batch, alerts=alerts, batches=batches,
    )
    _maybe_email_alerts(active.id, name, alerts)
    return out


def _maybe_email_alerts(pipeline_id: str, scenario: str, alerts: list[AlertOut]) -> None:
    """Email onboarded address when this pipeline raises alerts (demo notify path)."""
    if not alerts or not smtp_configured():
        return
    record = load_onboard()
    if record is None or record.pipeline_id != pipeline_id:
        return
    body = alert_email_body(
        pipeline_id=pipeline_id,
        scenario=scenario,
        ui_url="http://localhost:5173/scenarios",
        alerts=[a.model_dump() for a in alerts],
    )
    try:
        send_mail(
            record.email,
            f"[Driftline] {len(alerts)} alert(s) on {pipeline_id} / {scenario}",
            body,
        )
    except (OSError, smtplib.SMTPException, RuntimeError, TimeoutError):
        # Demo must not fail the scenario run if mail is down.
        return


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
    active = state.active_pipeline()
    if active is None:
        raise HTTPException(503, "No active pipeline")
    try:
        legacy = state.legacy_module()
        contract = state.contract()
        baselines = state.baselines()
    except (RuntimeError, AttributeError, TypeError) as exc:
        raise HTTPException(501, str(exc)) from exc
    scenarios = state.scenarios()
    stages = state.stages()
    gen = generate_for_pipeline(active.id)

    return [
        evaluate(
            "B0", legacy, contract, b0_no_checks(), scenarios,
            n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH,
            stages=stages, generate_batches=gen,
        ),
        evaluate(
            "B1", legacy, contract, b1_naive_schema_only(), scenarios,
            n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH,
            stages=stages, generate_batches=gen,
        ),
        evaluate(
            "ours", legacy, contract, ours(contract, baselines), scenarios,
            n_batches=N_BATCHES, events_per_batch=EVENTS_PER_BATCH,
            stages=stages, generate_batches=gen,
        ),
    ]


def _to_summary(report: EvaluationReport) -> EvaluationSummaryOut:
    return EvaluationSummaryOut(system=report.system_name, precision=report.precision,
                                recall=report.recall, mean_lag_batches=report.mean_lag_batches,
                                detection_matrix=report.detection_matrix())
