"""Code onboarding: analyze in place, store metadata only (no source copy)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from uuid import UUID

import pytest

from teleguard.onboard.code import (
    agent_checkpoints,
    analysis_from_record,
    confirmed_guarantees,
    confirmed_stages,
    generate_pipeline_id,
    list_records,
    load_record,
    metadata_to_pipeline,
    onboard_from_source,
    onboard_pipeline,
    register_record,
    save_record,
    set_guarantee_decision,
    set_output_store,
    set_stage_decision,
    set_stage_decisions,
    validate_pipeline_id,
)
from teleguard.onboard.output_store import MinioOutputStore, key_matches
from teleguard.pipeline_registry import PipelineRegistry

REPO = Path(__file__).resolve().parents[2]
USER_BEHAVIOR_SRC = REPO / "pipelines" / "user_behavior" / "src"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _make_remote_repo(tmp_path: Path) -> str:
    """Copy user_behavior src into a bare-cloneable git repo; return file:// URL."""
    import shutil

    src_repo = tmp_path / "upstream"
    src_repo.mkdir()
    shutil.copytree(USER_BEHAVIOR_SRC, src_repo / "src")
    _git(src_repo, "init")
    _git(src_repo, "config", "user.email", "test@example.com")
    _git(src_repo, "config", "user.name", "Test")
    _git(src_repo, "add", ".")
    _git(src_repo, "commit", "-m", "init")
    return src_repo.resolve().as_uri()


def test_generate_pipeline_id_is_uuid() -> None:
    pid = generate_pipeline_id()
    assert UUID(pid)
    assert pid != generate_pipeline_id()


def test_validate_pipeline_id_rejects_non_uuid() -> None:
    with pytest.raises(ValueError):
        validate_pipeline_id("client_ub")
    assert validate_pipeline_id("550e8400-e29b-41d4-a716-446655440000") == (
        "550e8400-e29b-41d4-a716-446655440000"
    )


def test_onboard_from_source_does_not_copy_tree(tmp_path: Path) -> None:
    record = onboard_from_source(
        USER_BEHAVIOR_SRC,
        name="Client UB",
        entry="run.run",
    )
    save_record(record, store_root=tmp_path)

    stored = tmp_path / record.pipeline_id
    assert (stored / "metadata.json").is_file()
    assert list(stored.rglob("*.py")) == []
    assert UUID(record.pipeline_id)
    assert record.source_path == str(USER_BEHAVIOR_SRC.resolve())
    assert record.stages == ["ingest", "filter_sessions", "aggregate"]
    assert all(s == "pending" for s in record.stage_status.values())
    assert record.findings


def test_round_trip_metadata_rebuilds_analysis(tmp_path: Path) -> None:
    record = onboard_from_source(USER_BEHAVIOR_SRC, name="Client UB")
    save_record(record, store_root=tmp_path)
    loaded = load_record(record.pipeline_id, store_root=tmp_path)
    assert loaded is not None
    analysis = analysis_from_record(loaded)
    assert [analysis.graph.node(s).label for s in analysis.stages] == record.stages
    assert len(analysis.findings) == len(record.findings)


def test_register_record_adds_to_registry(tmp_path: Path) -> None:
    record = onboard_from_source(USER_BEHAVIOR_SRC, name="Client UB")
    save_record(record, store_root=tmp_path)
    registry = PipelineRegistry()
    meta = register_record(registry, record)
    assert registry.get(record.pipeline_id) is meta
    assert meta.stages() == ["ingest", "filter_sessions", "aggregate"]
    assert meta.graph()["nodes"]
    assert meta.source_root == USER_BEHAVIOR_SRC.resolve()


def test_list_records_empty_store(tmp_path: Path) -> None:
    assert list_records(tmp_path) == []


def test_metadata_to_pipeline_matches_record() -> None:
    record = onboard_from_source(
        USER_BEHAVIOR_SRC,
        name="Client UB",
        description="demo",
    )
    meta = metadata_to_pipeline(record)
    assert meta.id == record.pipeline_id
    assert meta.name == "Client UB"
    assert meta.adapter_name == "python_pandas"
    raw = json.loads(json.dumps(record.to_json()))
    assert raw["pipeline_id"] == record.pipeline_id


def test_onboard_from_git_url_stores_url_not_tree(tmp_path: Path) -> None:
    git_url = _make_remote_repo(tmp_path)
    record = onboard_pipeline(
        name="From Git",
        git_url=git_url,
        source_subdir="src",
        entry="run.run",
    )
    save_record(record, store_root=tmp_path / "store")

    assert record.git_url == git_url
    assert record.source_subdir == "src"
    assert record.source_path == ""  # clone discarded
    assert record.stages == ["ingest", "filter_sessions", "aggregate"]
    assert list((tmp_path / "store" / record.pipeline_id).rglob("*.py")) == []


def test_onboard_rejects_both_or_neither_source() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        onboard_pipeline(name="x", source_path=USER_BEHAVIOR_SRC, git_url="https://x/y.git")
    with pytest.raises(ValueError, match="exactly one"):
        onboard_pipeline(name="x")


def test_confirm_stages_and_guarantees(tmp_path: Path) -> None:
    record = onboard_from_source(USER_BEHAVIOR_SRC, name="Client UB")
    assert confirmed_stages(record) == []
    assert confirmed_guarantees(record) == []

    record = set_stage_decisions(
        record,
        {"ingest": "confirmed", "aggregate": "confirmed", "filter_sessions": "rejected"},
    )
    assert confirmed_stages(record) == ["ingest", "aggregate"]
    cps = agent_checkpoints(record)
    assert {c["stage"] for c in cps} == {"ingest", "aggregate"}

    fid = str(record.findings[0]["id"])
    record = set_guarantee_decision(record, fid, "confirmed")
    assert len(confirmed_guarantees(record)) == 1
    save_record(record, store_root=tmp_path)
    loaded = load_record(record.pipeline_id, store_root=tmp_path)
    assert loaded is not None
    assert loaded.stage_status["ingest"] == "confirmed"
    assert loaded.guarantee_status[fid] == "confirmed"

    with pytest.raises(KeyError):
        set_stage_decision(record, "no_such_stage", "confirmed")
    with pytest.raises(ValueError):
        set_stage_decision(record, "ingest", "maybe")


def test_minio_output_store_fixed_stage_layout(tmp_path: Path) -> None:
    record = onboard_from_source(USER_BEHAVIOR_SRC, name="Client UB")
    record = set_stage_decisions(
        record, {"ingest": "confirmed", "aggregate": "confirmed"}
    )
    record = set_output_store(
        record,
        MinioOutputStore(
            endpoint="http://localhost:9000",
            bucket="demo",
            prefix="pipelines/billing/outputs",
        ),
    )
    save_record(record, store_root=tmp_path)
    loaded = load_record(record.pipeline_id, store_root=tmp_path)
    assert loaded is not None
    assert loaded.output_store is not None
    assert loaded.output_store["layout"] == "{prefix}/{stage}/"

    cps = {c["stage"]: c for c in agent_checkpoints(loaded)}
    assert cps["ingest"]["output_uri"] == (
        "s3://demo/pipelines/billing/outputs/ingest/"
    )
    assert cps["aggregate"]["output_uri"] == (
        "s3://demo/pipelines/billing/outputs/aggregate/"
    )


def test_each_stage_can_use_a_folder_a_file_or_a_table(tmp_path: Path) -> None:
    record = onboard_from_source(USER_BEHAVIOR_SRC, name="Client UB")
    record = set_stage_decisions(
        record, {"ingest": "confirmed", "filter_sessions": "confirmed", "aggregate": "confirmed"}
    )
    record = set_output_store(
        record,
        {
            "type": "minio",
            "endpoint": "http://localhost:9000",
            "bucket": "demo1",
            "secure": False,
            "stages": [
                {"stage": "ingest", "location": "demo1/outputs/ingest/"},
                {"stage": "filter_sessions", "location": "demo1/outputs/filter_sessions.csv"},
                {"stage": "aggregate", "location": "demo1/outputs/aggregate_*.parquet"},
            ],
        },
    )
    save_record(record, store_root=tmp_path)
    loaded = load_record(record.pipeline_id, store_root=tmp_path)
    assert loaded is not None
    cps = {c["stage"]: c for c in agent_checkpoints(loaded)}
    assert cps["ingest"]["output_uri"] == "s3://demo1/demo1/outputs/ingest/"
    assert cps["filter_sessions"]["object_location"] == "demo1/outputs/filter_sessions.csv"
    assert cps["aggregate"]["output_uri"] == "s3://demo1/demo1/outputs/aggregate_*.parquet"
    assert key_matches("demo1/outputs/ingest/run.csv", "demo1/outputs/ingest/")
    assert key_matches("demo1/outputs/filter_sessions.csv", "demo1/outputs/filter_sessions.csv")
    assert key_matches("demo1/outputs/aggregate_2026.parquet", "demo1/outputs/aggregate_*.parquet")
    assert not key_matches("demo1/outputs/other.csv", "demo1/outputs/ingest/")

    database = MinioOutputStore.from_json(
        {
            "type": "database",
            "dsn_env": "STAGE_DATABASE_URL",
            "stages": [{"stage": "ingest", "location": "public.ingest_events"}],
        }
    )
    assert database.describe("public.ingest_events") == "db://public.ingest_events"
    with pytest.raises(ValueError):
        MinioOutputStore.from_json(
            {"type": "database", "stages": [{"stage": "ingest", "location": "ingest;drop"}]}
        )


def test_shared_database_table_needs_one_table_and_a_column() -> None:
    store = MinioOutputStore.from_json(
        {
            "type": "database",
            "db_layout": "shared_table",
            "stage_column": "stage_name",
            "stages": [
                {"stage": "ingest", "location": "pipeline_output"},
                {"stage": "aggregate", "location": "pipeline_output"},
            ],
        }
    )
    assert store.stage_column == "stage_name"
    with pytest.raises(ValueError):
        MinioOutputStore.from_json(
            {
                "type": "database",
                "db_layout": "shared_table",
                "stage_column": "stage name",
                "stages": [{"stage": "ingest", "location": "pipeline_output"}],
            }
        )
