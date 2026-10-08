"""API response shapes. Separate from `teleguard.models` deliberately: those are the
engine's internal contracts (CLAUDE.md rule 7, change only by team agreement); these are
what the UI is allowed to depend on, and can change on this side alone.
"""

from __future__ import annotations

from pydantic import BaseModel


class ScenarioInfo(BaseModel):
    name: str
    fault_type: str
    description: str = ""


class LineageStepOut(BaseModel):
    node_id: str
    node_type: str
    label: str


class AlertOut(BaseModel):
    alert_id: str
    severity: str
    segment: str | None
    root_field: str | None
    message: str
    affected_outputs: list[str]
    lineage: list[LineageStepOut]
    first_batch: int | None


class BatchSummaryOut(BaseModel):
    batch: int
    passed: int
    warned: int
    failed: int
    blocked: bool
    failing_checks: list[str]


class ScenarioResultOut(BaseModel):
    scenario: str
    fault_type: str
    detected: bool
    lag_batches: int | None
    crashed_at_batch: int | None
    true_positive_alerts: int
    false_positive_alerts: int
    onset_batch: int
    alerts: list[AlertOut]
    batches: list[BatchSummaryOut]


class EvaluationSummaryOut(BaseModel):
    system: str
    precision: float
    recall: float
    mean_lag_batches: float | None
    detection_matrix: dict[str, bool]


class GuaranteeOut(BaseModel):
    id: str
    kind: str
    field: str | None
    message: str
    file: str
    line: int
    status: str


class GuaranteeDecisionIn(BaseModel):
    status: str  # "confirmed", "rejected"
