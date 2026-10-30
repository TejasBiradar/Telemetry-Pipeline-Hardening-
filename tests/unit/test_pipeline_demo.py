"""Pipeline demo runner: multi-pipeline frames, faults, and MinIO object names."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline_demo.catalog import list_pipelines, pipeline_by_id, source_dir
from pipeline_demo.faults import apply_fault, fault_by_id, list_faults
from pipeline_demo.runner import build_events, frames_from_events, object_key, sample_input
from pipeline_demo.store import store_stage_tables


def test_object_key_uses_stage_folder() -> None:
    assert object_key("demo/user_behavior/outputs", "ingest", "run1") == (
        "demo/user_behavior/outputs/ingest/run1.csv"
    )


def test_single_folder_key_keeps_every_stage_file_together() -> None:
    assert object_key("demo/user_behavior/outputs", "ingest", "run1", layout="single") == (
        "demo/user_behavior/outputs/ingest_run1.csv"
    )
    assert object_key("demo/user_behavior/outputs", "aggregate", "run1", layout="single") == (
        "demo/user_behavior/outputs/aggregate_run1.csv"
    )


def test_source_layouts_match_the_three_shapes() -> None:
    behavior = source_dir("user_behavior")
    payment = source_dir("payment_processing")
    shipment = source_dir("shipment_ledger")
    assert [path.name for path in behavior.glob("*.py")] == ["run.py"]
    payment_files = {path.name for path in payment.glob("*.py")}
    assert {"run.py", "ingest.py", "clean.py", "enrich.py", "reconcile.py", "rules.py"} <= payment_files
    assert any(shipment.glob("*.sql"))
    assert not any(shipment.glob("*.py"))


def test_catalog_lists_the_pipeline_shapes() -> None:
    ids = [spec.pipeline_id for spec in list_pipelines()]
    assert ids == [
        "user_behavior",
        "payment_processing",
        "shipment_ledger",
        "web_analytics",
    ]
    assert pipeline_by_id("user_behavior").kind == "python"
    assert pipeline_by_id("user_behavior").storage == "single"
    assert pipeline_by_id("payment_processing").storage == "subfolder"
    assert pipeline_by_id("shipment_ledger").storage == "database"
    assert pipeline_by_id("web_analytics").storage == "subfolder"
    assert pipeline_by_id("payment_processing").kind == "python"
    assert pipeline_by_id("shipment_ledger").kind == "sql"
    assert source_dir("payment_processing").name in {"src", "payment_processing"}
    assert any(source_dir("shipment_ledger").glob("*.sql"))


def test_clean_run_keeps_user_ids() -> None:
    frames = frames_from_events(
        build_events("user_behavior", 40),
        fault="clean",
        pipeline_id="user_behavior",
    )
    assert list(frames) == ["ingest", "filter_sessions", "aggregate"]
    assert frames["ingest"]["user_id"].notna().all()
    assert len(frames["aggregate"]) > 0


def test_payment_clean_run_has_reconcile_stage() -> None:
    frames = frames_from_events(
        build_events("payment_processing", 40),
        fault="clean",
        pipeline_id="payment_processing",
    )
    assert list(frames) == list(pipeline_by_id("payment_processing").stages)
    assert frames["ingest"]["user_id"].notna().all()
    assert len(frames["reconcile"]) > 0


def test_web_analytics_clean_run() -> None:
    frames = frames_from_events(
        build_events("web_analytics", 40),
        fault="clean",
        pipeline_id="web_analytics",
    )
    assert list(frames) == ["ingest", "clean", "enrich", "aggregate"]
    assert len(frames["aggregate"]) > 0


def test_new_nullable_nulls_only_the_named_version() -> None:
    frames = frames_from_events(
        build_events("user_behavior", 40),
        fault="new_nullable_web",
        pipeline_id="user_behavior",
    )
    ingest = frames["ingest"]
    targeted = ingest[ingest["client_version"] == "1.5.2"]
    others = ingest[ingest["client_version"] != "1.5.2"]
    assert targeted["user_id"].isna().any()
    assert others["user_id"].notna().all()
    assert frames["filter_sessions"]["user_id"].notna().all()


def test_payment_nullable_user_is_dropped_in_clean() -> None:
    frames = frames_from_events(
        build_events("payment_processing", 40),
        fault="new_nullable_user",
        pipeline_id="payment_processing",
    )
    assert frames["ingest"]["user_id"].isna().any()
    assert frames["clean"]["user_id"].notna().all()


def test_unit_change_shrinks_duration_for_one_version() -> None:
    clean = apply_fault(build_events("user_behavior", 40), "clean", pipeline_id="user_behavior")
    changed = apply_fault(
        build_events("user_behavior", 40),
        "unit_change_android",
        pipeline_id="user_behavior",
    )
    clean_hit = next(event for event in clean if event["client_version"] == "5.2.0")
    changed_hit = next(event for event in changed if event["client_version"] == "5.2.0")
    assert changed_hit["payload"]["duration_ms"] == clean_hit["payload"]["duration_ms"] / 1000.0


def test_feed_stops_removes_one_version() -> None:
    frames = frames_from_events(
        build_events("user_behavior", 40),
        fault="feed_stops_ios",
        pipeline_id="user_behavior",
    )
    versions = set(frames["ingest"]["client_version"])
    assert "6.0.1" not in versions
    assert "1.2.0" in versions


def test_type_change_fails_the_numeric_stage() -> None:
    with pytest.raises(TypeError):
        frames_from_events(
            build_events("user_behavior", 40),
            fault="type_change_android",
            pipeline_id="user_behavior",
        )


def test_payment_type_change_fails() -> None:
    with pytest.raises(TypeError):
        frames_from_events(
            build_events("payment_processing", 40),
            fault="type_change_amount",
            pipeline_id="payment_processing",
        )


def test_shipment_clean_run_drops_nothing_required() -> None:
    frames = frames_from_events(
        build_events("shipment_ledger", 40),
        fault="clean",
        pipeline_id="shipment_ledger",
    )
    assert list(frames) == ["landed", "cleaned", "daily"]
    assert frames["landed"]["shipment_id"].notna().all()
    assert len(frames["daily"]) > 0
    assert frames["cleaned"]["weight_kg"].mean() == pytest.approx(
        frames["landed"]["weight_g"].mean() / 1000.0
    )


def test_shipment_null_id_is_dropped_in_cleaned() -> None:
    frames = frames_from_events(
        build_events("shipment_ledger", 40),
        fault="null_shipment_id",
        pipeline_id="shipment_ledger",
    )
    assert frames["landed"]["shipment_id"].isna().any()
    assert frames["cleaned"]["shipment_id"].notna().all()


def test_shipment_weight_text_fails() -> None:
    with pytest.raises(TypeError):
        frames_from_events(
            build_events("shipment_ledger", 40),
            fault="weight_as_text",
            pipeline_id="shipment_ledger",
        )


def test_faults_differ_by_pipeline() -> None:
    payment_ids = {fault.fault_id for fault in list_faults("payment_processing")}
    behavior_ids = {fault.fault_id for fault in list_faults("user_behavior")}
    shipment_ids = {fault.fault_id for fault in list_faults("shipment_ledger")}
    web_ids = {fault.fault_id for fault in list_faults("web_analytics")}
    behavior_labels = {fault.label for fault in list_faults("user_behavior")}
    web_labels = {fault.label for fault in list_faults("web_analytics")}
    assert "new_nullable_user" in payment_ids
    assert "new_nullable_user" not in behavior_ids
    assert "new_nullable_web" in behavior_ids
    assert "weight_already_kg" in shipment_ids
    assert "weight_already_kg" not in payment_ids
    assert "anonymous_web_hits" in web_ids
    assert "anonymous_web_hits" not in behavior_ids
    assert behavior_labels.isdisjoint(web_labels)


def test_web_analytics_alias_fault_runs() -> None:
    frames = frames_from_events(
        build_events("web_analytics", 40),
        fault="anonymous_web_hits",
        pipeline_id="web_analytics",
    )
    assert frames["ingest"]["user_id"].isna().any()
    assert frames["clean"]["user_id"].notna().all()


def test_unknown_fault_is_rejected() -> None:
    with pytest.raises(ValueError):
        fault_by_id("not-a-fault")


def test_sample_input_is_the_faulted_batch() -> None:
    sample = sample_input("user_behavior", "clean", limit=3)
    assert sample["row_count"] == 40
    assert sample["shown"] == 3
    rows = sample["rows"]
    assert isinstance(rows, list)
    assert "duration_ms" in rows[0]
    assert "payload" not in rows[0]


def test_shipment_tables_append_a_run_id() -> None:
    dsn = os.environ.get(
        "STAGE_DATABASE_URL",
        "postgresql://teleguard:teleguard@localhost:5432/teleguard",
    )
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError:
        pytest.skip("Postgres is not running at STAGE_DATABASE_URL")
    frames = frames_from_events(
        build_events("shipment_ledger", 4),
        fault="clean",
        pipeline_id="shipment_ledger",
    )
    locations = store_stage_tables(
        dsn,
        "shipment_ledger",
        frames,
        ("landed", "cleaned", "daily"),
        "run-test",
    )
    assert locations[0] == "db://shipment_ledger_landed"
    try:
        with psycopg.connect(dsn) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM shipment_ledger_landed WHERE run_id = %s",
                ("run-test",),
            ).fetchone()
        assert count is not None
        assert count[0] == 4
    finally:
        with psycopg.connect(dsn) as conn:
            conn.execute("DELETE FROM shipment_ledger_landed WHERE run_id = %s", ("run-test",))
            conn.execute("DELETE FROM shipment_ledger_cleaned WHERE run_id = %s", ("run-test",))
            conn.execute("DELETE FROM shipment_ledger_daily WHERE run_id = %s", ("run-test",))
            conn.commit()


def test_empty_prefix_still_uses_stage_folder() -> None:
    assert object_key("", "aggregate", "run1") == "aggregate/run1.csv"
