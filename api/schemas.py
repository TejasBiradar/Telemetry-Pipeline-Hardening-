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


class OnboardIn(BaseModel):
    email: str
    pipeline_id: str
    source_note: str = ""


class OnboardOut(BaseModel):
    email: str
    pipeline_id: str
    source_note: str = ""
    smtp_configured: bool
    email_sent: str | None = None
    email_error: str | None = None


class CodeOnboardIn(BaseModel):
    """Register client pipeline code: analyze local path or git URL.

    Provide exactly one of ``source_path`` or ``git_url``.
    ``pipeline_id`` is assigned by the server (UUID).
    """

    name: str
    source_path: str | None = None
    git_url: str | None = None
    git_ref: str = "HEAD"
    source_subdir: str = ""
    entry: str = "run.run"
    adapter: str | None = None
    description: str = ""
    select: bool = True


class OnboardFindingOut(BaseModel):
    id: str
    kind: str
    field: str | None = None
    message: str
    file: str = ""
    line: int = 0


class CodeOnboardSummaryOut(BaseModel):
    pipeline_id: str
    name: str
    adapter: str
    analyzed_at: str
    findings_count: int
    confirmed_stages: list[str]
    has_output_store: bool


class CodeOnboardOut(BaseModel):
    pipeline_id: str
    name: str
    source_path: str
    git_url: str = ""
    git_ref: str = ""
    source_subdir: str = ""
    adapter: str
    stages: list[str]
    checkpoints: list[dict[str, str]]
    findings: list[OnboardFindingOut] = []
    findings_count: int
    stage_status: dict[str, str]
    guarantee_status: dict[str, str] = {}
    confirmed_stages: list[str] = []
    agent_checkpoints: list[dict[str, str]] = []
    output_store: dict[str, object] | None = None
    metadata_path: str
    analyzed_at: str


class DecisionIn(BaseModel):
    status: str  # pending | confirmed | rejected


class StageDecisionsIn(BaseModel):
    decisions: dict[str, str]


class StageLocationIn(BaseModel):
    """Folder, object/glob, or database table for one stage."""

    stage: str
    location: str


class MinioOutputStoreIn(BaseModel):
    """MinIO or database destinations. Each stage carries its own location."""

    kind: str = "minio"
    endpoint: str = ""
    bucket: str = ""
    prefix: str = ""
    secure: bool = False
    access_key_env: str = "MINIO_ACCESS_KEY"
    secret_key_env: str = "MINIO_SECRET_KEY"
    dsn_env: str = "STAGE_DATABASE_URL"
    db_layout: str = ""
    stage_column: str = ""
    stages: list[StageLocationIn] = []


class AgentRunIn(BaseModel):
    pipeline_id: str
    stage: str
    checkpoint: str
    object_key: str
    batch_id: str
    observed_at: str
    results: list[dict[str, object]]
    failed: int
    passed: int


class AgentRunOut(BaseModel):
    pipeline_id: str
    stage: str
    checkpoint: str
    object_key: str
    batch_id: str
    observed_at: str
    results: list[dict[str, object]]
    failed: int
    passed: int
