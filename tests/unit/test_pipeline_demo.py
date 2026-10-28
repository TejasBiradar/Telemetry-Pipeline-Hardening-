"""Pipeline demo runner: multi-pipeline frames, faults, and MinIO object names."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline_demo.catalog import list_pipelines, pipeline_by_id, source_dir
from pipeline_demo.faults import apply_fault, fault_by_id, list_faults
from pipeline_demo.runner import build_events, frames_from_events, object_key


def test_object_key_uses_stage_folder() -> None:
    assert object_key("demo/user_behavior/outputs", "ingest", "run1") == (
        "demo/user_behavior/outputs/ingest/run1.csv"
    )


def test_catalog_lists_three_pipelines() -> None:
    ids = [spec.pipeline_id for spec in list_pipelines()]
    assert ids == ["user_behavior", "payment_processing", "web_analytics"]
    assert source_dir("payment_processing").name in {"src", "payment_processing"}


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


def test_faults_differ_by_pipeline() -> None:
    payment_ids = {fault.fault_id for fault in list_faults("payment_processing")}
    behavior_ids = {fault.fault_id for fault in list_faults("user_behavior")}
    web_ids = {fault.fault_id for fault in list_faults("web_analytics")}
    behavior_labels = {fault.label for fault in list_faults("user_behavior")}
    web_labels = {fault.label for fault in list_faults("web_analytics")}
    assert "new_nullable_user" in payment_ids
    assert "new_nullable_user" not in behavior_ids
    assert "new_nullable_web" in behavior_ids
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


def test_empty_prefix_still_uses_stage_folder() -> None:
    assert object_key("", "aggregate", "run1") == "aggregate/run1.csv"
