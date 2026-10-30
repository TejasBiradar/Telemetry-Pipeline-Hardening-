"""Registration and check alerts persist in Postgres when a DSN is configured."""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from teleguard.pg_store import append_agent_run, save_registration


def test_registration_stages_guarantees_and_alerts_land_in_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    dsn = "postgresql://teleguard:teleguard@localhost:5432/teleguard"
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError:
        pytest.skip("Postgres is not running at STAGE_DATABASE_URL")
    monkeypatch.setenv("STAGE_DATABASE_URL", dsn)
    pipeline_id = str(uuid4())
    guarantee_id = "required_field:price:pipeline.py:10"
    try:
        save_registration(
            {
                "pipeline_id": pipeline_id,
                "name": "Probe",
                "description": "",
                "entry": "pipeline.run_pipeline",
                "adapter": "python_pandas",
                "source_path": "",
                "git_url": "https://example.com/repo.git",
                "git_ref": "HEAD",
                "source_subdir": "src",
                "analyzed_at": "2026-10-31T00:00:00Z",
                "stages": ["read_data", "clean_data"],
                "stage_ids": ["stage:1:read_data", "stage:2:clean_data"],
                "stage_status": {"read_data": "pending", "clean_data": "confirmed"},
                "findings": [
                    {
                        "id": guarantee_id,
                        "kind": "required_field",
                        "field": "price",
                        "message": "price is required",
                        "evidence": {"file": "pipeline.py", "line": 10, "snippet": ""},
                    }
                ],
                "guarantee_status": {guarantee_id: "pending"},
                "checkpoints": [
                    {
                        "name": "after_read_data",
                        "after_stage": "stage:1:read_data",
                        "attach": "in_process_hook",
                        "location": "",
                    }
                ],
                "graph": {"nodes": [], "edges": []},
                "output_store": None,
            }
        )
        append_agent_run(
            {
                "pipeline_id": pipeline_id,
                "stage": "clean_data",
                "checkpoint": "after_clean_data",
                "object_key": "clean_data/run.csv",
                "batch_id": "clean_data/run.csv",
                "observed_at": "2026-10-31T00:01:00Z",
                "failed": 1,
                "passed": 0,
                "results": [
                    {
                        "check": "nulls:price",
                        "status": "fail",
                        "checkpoint": "after_clean_data",
                        "field": "price",
                        "message": "price has nulls",
                    }
                ],
            }
        )
        with psycopg.connect(dsn) as conn:
            stages = conn.execute(
                "SELECT stage_label, status FROM registered_stages "
                "WHERE pipeline_id = %s ORDER BY position",
                (pipeline_id,),
            ).fetchall()
            guarantee = conn.execute(
                "SELECT status, field_name FROM registered_guarantees "
                "WHERE pipeline_id = %s AND guarantee_id = %s",
                (pipeline_id, guarantee_id),
            ).fetchone()
            alert = conn.execute(
                "SELECT status, check_name FROM check_alerts WHERE pipeline_id = %s",
                (pipeline_id,),
            ).fetchone()
        assert stages == [("read_data", "pending"), ("clean_data", "confirmed")]
        assert guarantee == ("pending", "price")
        assert alert == ("fail", "nulls:price")
    finally:
        with psycopg.connect(dsn) as conn:
            conn.execute("DELETE FROM check_alerts WHERE pipeline_id = %s", (pipeline_id,))
            conn.execute("DELETE FROM agent_runs WHERE pipeline_id = %s", (pipeline_id,))
            conn.execute("DELETE FROM registered_pipelines WHERE pipeline_id = %s", (pipeline_id,))
            conn.commit()
