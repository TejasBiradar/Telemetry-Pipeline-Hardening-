"""Watcher agent: guarantee→check mapping and local results store."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from teleguard.agent.guarantee_checks import checks_from_guarantees
from teleguard.agent.results_store import AgentRun, append_run, latest_run, list_runs
from teleguard.models import BatchContext, Status


def test_checks_from_guarantees_schema_and_nulls() -> None:
    guarantees = [
        {
            "id": "required_field:user_id:a.py:1",
            "kind": "required_field",
            "field": "user_id",
            "message": "required",
        },
        {
            "id": "unit_conversion:duration_ms:a.py:2",
            "kind": "unit_conversion",
            "field": "duration_ms",
            "message": "ms",
        },
    ]
    checks = checks_from_guarantees("after_ingest", guarantees)
    names = {c.name for c in checks}
    assert "volume" in names
    assert "schema:user_id" in names
    assert "null_rate:user_id" in names
    assert "schema:duration_ms" in names
    assert "null_rate:duration_ms" not in names

    df = pd.DataFrame({"user_id": [None] * 40, "duration_ms": list(range(40))})
    ctx = BatchContext(pipeline="p", batch_id="b1")
    results = [r for c in checks for r in c.run(df, ctx)]
    assert any(r.status is Status.FAIL and r.field == "user_id" for r in results)


def test_checks_skip_fields_absent_from_stage_columns() -> None:
    """Aggregate stages drop row-level fields; do not schema-fail them there."""
    guarantees = [
        {
            "id": "required_field:user_id:a.py:1",
            "kind": "required_field",
            "field": "user_id",
            "message": "required",
        },
        {
            "id": "unit_conversion:amount_cents:a.py:2",
            "kind": "unit_conversion",
            "field": "amount_cents",
            "message": "cents",
        },
    ]
    reconcile_cols = ["transaction_date", "merchant_region", "unique_users"]
    checks = checks_from_guarantees(
        "after_reconcile",
        guarantees,
        columns=reconcile_cols,
    )
    names = {c.name for c in checks}
    assert names == {"volume"}

    early = checks_from_guarantees(
        "after_clean",
        guarantees,
        columns=["user_id", "amount_cents", "status"],
    )
    early_names = {c.name for c in early}
    assert "schema:user_id" in early_names
    assert "null_rate:user_id" in early_names
    assert "schema:amount_cents" in early_names


def test_append_and_latest_run(tmp_path: Path) -> None:
    run = AgentRun(
        pipeline_id="11111111-1111-1111-1111-111111111111",
        stage="ingest",
        checkpoint="after_ingest",
        object_key="prefix/ingest/a.csv",
        batch_id="prefix/ingest/a.csv",
        observed_at="2026-01-01T00:00:00Z",
        results=[{"check": "volume", "status": "pass"}],
        failed=0,
        passed=1,
    )
    append_run(run, store_root=tmp_path)
    assert latest_run(run.pipeline_id, store_root=tmp_path) == run
    assert len(list_runs(run.pipeline_id, store_root=tmp_path)) == 1
