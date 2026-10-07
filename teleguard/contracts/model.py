"""Contract model: what each checkpoint must satisfy, loaded from YAML.

A contract is a draft until it is generated from A's reviewed `GUARANTEES.md` (CLAUDE.md:
every claim needs evidence). Until that review is done, this engine is built and tested
against a hand-written placeholder (`pipelines/<name>/contracts.yaml`) with the same shape,
so B's work is not blocked on A's review step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from teleguard.models import CheckType


class RangeSpec(BaseModel):
    min: float | None = None
    max: float | None = None
    max_violation_rate: float = 0.0  # share of out-of-range values tolerated before FAIL


class CheckSpec(BaseModel):
    """One check to run for one field. Only the fields relevant to `type` are read."""

    type: CheckType
    dtype: str | None = None  # schema
    max_null_rate: float | None = None  # nulls
    range: RangeSpec | None = None  # range
    allowed: list[str] | None = None  # schema, used as a key-set check
    max_distinct: int | None = None  # schema, used as a cardinality check
    baseline_stat: str = "median"  # unit
    log_ratio_threshold: float | None = None  # unit
    psi_threshold: float = 0.10  # numeric_drift
    ks_alpha: float = 0.01  # numeric_drift
    oov_threshold: float = 0.15  # text_drift
    template_threshold: float = 0.30  # text_drift


class FieldContract(BaseModel):
    checks: list[CheckSpec] = Field(default_factory=list)


class CheckpointContract(BaseModel):
    checkpoint: str
    segment_by: str | None = None
    min_rows: int | None = None
    max_rows: int | None = None
    # Checkpoint-wide, not field-specific — a segment going silent isn't one field's problem.
    check_segment_volume: bool = False
    min_share_of_baseline: float = 0.5
    fields: dict[str, FieldContract] = Field(default_factory=dict)


class Contract(BaseModel):
    pipeline: str
    checkpoints: list[CheckpointContract] = Field(default_factory=list)

    def for_checkpoint(self, name: str) -> CheckpointContract | None:
        return next((c for c in self.checkpoints if c.checkpoint == name), None)


def load_contract(path: Path) -> Contract:
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    return Contract.model_validate(data)
