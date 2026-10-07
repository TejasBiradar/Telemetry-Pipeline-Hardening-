"""Shared data contracts. Changes need all three team members to agree (CLAUDE.md rule 7)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GuardMode(str, Enum):
    OFF = "off"
    OBSERVE = "observe"
    ENFORCE = "enforce"


class Status(str, Enum):
    PASS = "pass"  # nosec B105 - a check status, not a credential; bandit's heuristic misfires here
    WARN = "warn"
    FAIL = "fail"
    ERROR = "error"  # the check itself crashed; recorded, never raised
    INSUFFICIENT_DATA = "insufficient_data"  # too few rows to judge; never a failure


class CheckType(str, Enum):
    SCHEMA = "schema"
    NULLS = "nulls"
    RANGE = "range"
    UNIT = "unit"
    VOLUME = "volume"
    NUMERIC_DRIFT = "numeric_drift"
    TEXT_DRIFT = "text_drift"


class BatchContext(BaseModel):
    pipeline: str
    batch_id: str
    segment_column: str | None = None
    event_time: datetime | None = None


class CheckResult(BaseModel):
    check: str
    check_type: CheckType
    checkpoint: str
    status: Status
    field: str | None = None
    segment: str | None = None
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class LineageStep(BaseModel):
    node_id: str
    node_type: str
    label: str


class Alert(BaseModel):
    alert_id: str
    pipeline: str
    batch_id: str
    severity: str
    message: str
    root_field: str | None = None
    segment: str | None = None
    lineage: list[LineageStep] = Field(default_factory=list)
    affected_outputs: list[str] = Field(default_factory=list)
