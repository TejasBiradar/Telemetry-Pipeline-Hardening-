"""Filter a draft contract so only *confirmed* guarantees are enforced at runtime.

Pending and rejected findings do not contribute checks. If nothing is confirmed, the
returned contract has no checkpoints — Checks ON behaves like an empty check set.
"""

from __future__ import annotations

from typing import Any

from teleguard.contracts.model import CheckpointContract, Contract, FieldContract
from teleguard.findings import FindingKind
from teleguard.models import CheckType

# Finding kind → check types that enforce it. Empty set = checkpoint-level only (see below).
_KIND_TO_FIELD_CHECKS: dict[FindingKind, frozenset[CheckType]] = {
    FindingKind.UNIT_CONVERSION: frozenset(
        {CheckType.UNIT, CheckType.RANGE, CheckType.NUMERIC_DRIFT}
    ),
    FindingKind.REQUIRED_FIELD: frozenset({CheckType.NULLS}),
    FindingKind.ROW_FILTER: frozenset(),  # enables volume / segment volume
    FindingKind.DEDUP_KEY: frozenset({CheckType.SCHEMA}),
    FindingKind.UNMAPPED_TO_NULL: frozenset({CheckType.SCHEMA}),
    FindingKind.DEFAULT_FILL: frozenset({CheckType.SCHEMA, CheckType.NULLS}),
    FindingKind.KEYWORD_MATCH: frozenset({CheckType.TEXT_DRIFT}),
    FindingKind.STRING_FORMAT: frozenset({CheckType.TEXT_DRIFT}),
    FindingKind.TIMESTAMP_UNIT: frozenset({CheckType.SCHEMA, CheckType.UNIT}),
    FindingKind.TIMEZONE: frozenset({CheckType.SCHEMA}),
    FindingKind.GROUP_KEY_DROPS_NULLS: frozenset({CheckType.NULLS}),
    FindingKind.NULL_LOOKALIKE_VALUE: frozenset({CheckType.NULLS}),
    FindingKind.RUNTIME_COLUMNS: frozenset(),
    FindingKind.UNUSED_FIELD: frozenset(),
}


def _stem(name: str) -> str:
    """Strip common unit/suffix noise so duration_ms matches duration_s."""
    for suf in ("_ms", "_s", "_usd", "_cents", "_id", "_rate", "_count"):
        if name.endswith(suf) and len(name) > len(suf) + 1:
            return name[: -len(suf)]
    return name


def fields_related(a: str, b: str) -> bool:
    """True when two field names refer to the same logical column family."""
    return a == b or _stem(a) == _stem(b)


def _confirmed_findings(
    findings: list[dict[str, Any]], decisions: dict[str, Any]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for finding in findings:
        fid = str(finding.get("id", ""))
        status = decisions.get(fid, {}).get("status", "pending")
        if status == "confirmed":
            out.append(finding)
    return out


def contract_for_decisions(
    contract: Contract,
    findings: list[dict[str, Any]],
    decisions: dict[str, Any],
) -> Contract:
    """Return a copy of ``contract`` containing only checks backed by confirmed findings."""
    confirmed = _confirmed_findings(findings, decisions)
    if not confirmed:
        return Contract(pipeline=contract.pipeline, checkpoints=[])

    # field stem / name → allowed check types
    allowed_types: dict[str, set[CheckType]] = {}
    enable_volume = False

    for finding in confirmed:
        try:
            kind = FindingKind(str(finding["kind"]))
        except ValueError:
            continue
        mapped = _KIND_TO_FIELD_CHECKS.get(kind, frozenset())
        if kind is FindingKind.ROW_FILTER:
            enable_volume = True
        field = finding.get("field")
        if isinstance(field, str) and field:
            allowed_types.setdefault(field, set()).update(mapped)
            allowed_types.setdefault(_stem(field), set()).update(mapped)

    new_checkpoints: list[CheckpointContract] = []
    for cp in contract.checkpoints:
        new_fields: dict[str, FieldContract] = {}
        for fname, field_contract in cp.fields.items():
            matching: set[CheckType] = set()
            for key, types in allowed_types.items():
                if fields_related(fname, key) or fname == key or _stem(fname) == key:
                    matching |= types
            kept = [spec for spec in field_contract.checks if spec.type in matching]
            if kept:
                new_fields[fname] = FieldContract(checks=list(kept))

        keep_volume = enable_volume and (cp.min_rows is not None or cp.max_rows is not None)
        keep_segment = enable_volume and cp.check_segment_volume
        if not new_fields and not keep_volume and not keep_segment:
            continue

        new_checkpoints.append(
            CheckpointContract(
                checkpoint=cp.checkpoint,
                segment_by=cp.segment_by if (new_fields or keep_segment) else None,
                min_rows=cp.min_rows if keep_volume else None,
                max_rows=cp.max_rows if keep_volume else None,
                check_segment_volume=keep_segment,
                min_share_of_baseline=cp.min_share_of_baseline,
                fields=new_fields,
            )
        )

    return Contract(pipeline=contract.pipeline, checkpoints=new_checkpoints)


def contract_needs_baselines(contract: Contract) -> bool:
    """True if any remaining check needs a BaselineStore."""
    for cp in contract.checkpoints:
        if cp.check_segment_volume:
            return True
        for field in cp.fields.values():
            for spec in field.checks:
                if spec.type in (
                    CheckType.UNIT,
                    CheckType.NUMERIC_DRIFT,
                    CheckType.TEXT_DRIFT,
                ):
                    return True
    return False


def count_enforced_checks(contract: Contract) -> int:
    """Count field-level check specs (+ volume gates) in a filtered contract."""
    n = 0
    for cp in contract.checkpoints:
        if cp.min_rows is not None or cp.max_rows is not None:
            n += 1
        if cp.check_segment_volume:
            n += 1
        for field in cp.fields.values():
            n += len(field.checks)
    return n
