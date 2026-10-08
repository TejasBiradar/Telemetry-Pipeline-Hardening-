"""Confirmed guarantees gate which contract checks run at trigger time."""

from __future__ import annotations

from teleguard.contracts.decisions_filter import (
    contract_for_decisions,
    contract_needs_baselines,
    count_enforced_checks,
    fields_related,
)
from teleguard.contracts.model import (
    CheckpointContract,
    CheckSpec,
    Contract,
    FieldContract,
    RangeSpec,
)
from teleguard.models import CheckType


def _contract() -> Contract:
    return Contract(
        pipeline="demo",
        checkpoints=[
            CheckpointContract(
                checkpoint="after_ingest",
                segment_by="client_version",
                min_rows=50,
                fields={
                    "user_id": FieldContract(
                        checks=[CheckSpec(type=CheckType.NULLS, max_null_rate=0.1)]
                    ),
                    "duration_ms": FieldContract(
                        checks=[CheckSpec(type=CheckType.SCHEMA, dtype="numeric")]
                    ),
                    "error_message": FieldContract(
                        checks=[CheckSpec(type=CheckType.TEXT_DRIFT, oov_threshold=0.2)]
                    ),
                },
            ),
            CheckpointContract(
                checkpoint="after_clean",
                segment_by="client_version",
                check_segment_volume=True,
                fields={
                    "duration_s": FieldContract(
                        checks=[
                            CheckSpec(
                                type=CheckType.UNIT,
                                baseline_stat="median",
                                log_ratio_threshold=0.3,
                            ),
                            CheckSpec(
                                type=CheckType.RANGE,
                                range=RangeSpec(min=0, max=300),
                            ),
                        ]
                    ),
                },
            ),
        ],
    )


def _findings() -> list[dict[str, object]]:
    return [
        {
            "id": "required_field:user_id:run.py:50",
            "kind": "required_field",
            "field": "user_id",
        },
        {
            "id": "unit_conversion:duration_ms:run.py:53",
            "kind": "unit_conversion",
            "field": "duration_ms",
        },
        {
            "id": "row_filter:action:run.py:90",
            "kind": "row_filter",
            "field": "action",
        },
        {
            "id": "keyword_match:error_message:run.py:60",
            "kind": "keyword_match",
            "field": "error_message",
        },
    ]


def test_fields_related_matches_unit_suffix_variants() -> None:
    assert fields_related("duration_ms", "duration_s")
    assert not fields_related("user_id", "duration_s")


def test_nothing_confirmed_means_no_checks() -> None:
    findings = _findings()
    decisions = {f["id"]: {"status": "rejected"} for f in findings}
    filtered = contract_for_decisions(_contract(), findings, decisions)  # type: ignore[arg-type]
    assert filtered.checkpoints == []
    assert count_enforced_checks(filtered) == 0
    assert contract_needs_baselines(filtered) is False


def test_confirm_unit_enables_duration_s_unit_and_range() -> None:
    findings = _findings()
    decisions = {
        "unit_conversion:duration_ms:run.py:53": {"status": "confirmed"},
        "required_field:user_id:run.py:50": {"status": "rejected"},
    }
    filtered = contract_for_decisions(_contract(), findings, decisions)
    assert [c.checkpoint for c in filtered.checkpoints] == ["after_clean"]
    clean = filtered.for_checkpoint("after_clean")
    assert clean is not None
    types = {s.type for s in clean.fields["duration_s"].checks}
    assert types == {CheckType.UNIT, CheckType.RANGE}
    assert contract_needs_baselines(filtered) is True


def test_confirm_required_field_keeps_nulls_only() -> None:
    findings = _findings()
    decisions = {"required_field:user_id:run.py:50": {"status": "confirmed"}}
    filtered = contract_for_decisions(_contract(), findings, decisions)
    ingest = filtered.for_checkpoint("after_ingest")
    assert ingest is not None
    assert list(ingest.fields) == ["user_id"]
    assert ingest.fields["user_id"].checks[0].type is CheckType.NULLS
    assert ingest.min_rows is None  # volume only when row_filter confirmed
    assert contract_needs_baselines(filtered) is False


def test_confirm_row_filter_enables_volume_gates() -> None:
    findings = _findings()
    decisions = {"row_filter:action:run.py:90": {"status": "confirmed"}}
    filtered = contract_for_decisions(_contract(), findings, decisions)
    ingest = filtered.for_checkpoint("after_ingest")
    clean = filtered.for_checkpoint("after_clean")
    assert ingest is not None and ingest.min_rows == 50
    assert clean is not None and clean.check_segment_volume is True
    assert contract_needs_baselines(filtered) is True


def test_pending_does_not_enforce() -> None:
    findings = _findings()
    filtered = contract_for_decisions(_contract(), findings, {})
    assert filtered.checkpoints == []
