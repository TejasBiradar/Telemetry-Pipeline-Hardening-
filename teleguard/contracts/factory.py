"""Build runnable checks from a loaded `Contract` plus a `BaselineStore`.

One `numeric_drift` entry expands into both PSI and KS-test (the two are complementary:
PSI is the readable, threshold-based signal; KS adds a statistical-significance check on
top). One `text_drift` entry expands into OOV-rate and template-drift the same way.
"""

from __future__ import annotations

from teleguard.checks.base import Check
from teleguard.checks.gates import (
    CardinalityCheck,
    KeySetCheck,
    NullRateCheck,
    RangeCheck,
    SchemaCheck,
    VolumeCheck,
)
from teleguard.checks.segment_volume import SegmentVolumeCheck
from teleguard.checks.unit import UnitConsistencyCheck
from teleguard.contracts.model import CheckSpec, Contract, RangeSpec
from teleguard.drift.baseline import BaselineStore
from teleguard.drift.numeric import KsCheck, PsiCheck
from teleguard.drift.text import OovRateCheck, TemplateDriftCheck
from teleguard.models import CheckType


def build_checks(contract: Contract, checkpoint: str, baselines: BaselineStore) -> list[Check]:
    cp = contract.for_checkpoint(checkpoint)
    if cp is None:
        return []
    checks: list[Check] = []
    if cp.min_rows is not None or cp.max_rows is not None:
        checks.append(VolumeCheck(checkpoint, cp.min_rows, cp.max_rows))
    if cp.check_segment_volume:
        checks.append(SegmentVolumeCheck(checkpoint, baselines, cp.min_share_of_baseline))
    for field_name, field_contract in cp.fields.items():
        for spec in field_contract.checks:
            checks.extend(_build_one(checkpoint, field_name, spec, baselines))
    return checks


def _build_one(checkpoint: str, field: str, spec: CheckSpec,
               baselines: BaselineStore) -> list[Check]:
    if spec.type is CheckType.SCHEMA:
        if spec.allowed is not None:
            return [KeySetCheck(checkpoint, field, spec.allowed)]
        if spec.max_distinct is not None:
            return [CardinalityCheck(checkpoint, field, spec.max_distinct)]
        return [SchemaCheck(checkpoint, field, spec.dtype)]
    if spec.type is CheckType.NULLS:
        return [NullRateCheck(checkpoint, field, spec.max_null_rate or 0.0)]
    if spec.type is CheckType.RANGE:
        r = spec.range or RangeSpec()
        return [RangeCheck(checkpoint, field, r.min, r.max, r.max_violation_rate)]
    if spec.type is CheckType.UNIT:
        return [UnitConsistencyCheck(checkpoint, field, baselines, spec.baseline_stat,
                                     spec.log_ratio_threshold or 0.3)]
    if spec.type is CheckType.VOLUME:
        return []  # volume is checkpoint-wide; handled from CheckpointContract, not per field
    if spec.type is CheckType.NUMERIC_DRIFT:
        return [PsiCheck(checkpoint, field, baselines, spec.psi_threshold),
                KsCheck(checkpoint, field, baselines, spec.ks_alpha)]
    if spec.type is CheckType.TEXT_DRIFT:
        return [OovRateCheck(checkpoint, field, baselines, spec.oov_threshold),
                TemplateDriftCheck(checkpoint, field, baselines, spec.template_threshold)]
    raise ValueError(f"no check builder for {spec.type}")  # pragma: no cover - exhaustive enum
