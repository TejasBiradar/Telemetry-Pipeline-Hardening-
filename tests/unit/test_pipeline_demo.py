"""Pipeline demo runner: stage frames, fault application, and MinIO object names."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "user_behavior" / "src"))
sys.path.insert(0, str(ROOT))

from pipeline_demo.faults import apply_fault, fault_by_id
from pipeline_demo.runner import build_events, frames_from_events, object_key


def test_object_key_uses_stage_folder() -> None:
    assert object_key("demo/user_behavior/outputs", "ingest", "run1") == (
        "demo/user_behavior/outputs/ingest/run1.csv"
    )


def test_clean_run_keeps_user_ids() -> None:
    frames = frames_from_events(build_events(40), fault="clean")
    assert list(frames) == ["ingest", "filter_sessions", "aggregate"]
    assert frames["ingest"]["user_id"].notna().all()
    assert len(frames["aggregate"]) > 0


def test_new_nullable_nulls_only_the_named_version() -> None:
    frames = frames_from_events(build_events(40), fault="new_nullable_web")
    ingest = frames["ingest"]
    targeted = ingest[ingest["client_version"] == "1.5.2"]
    others = ingest[ingest["client_version"] != "1.5.2"]
    assert targeted["user_id"].isna().any()
    assert others["user_id"].notna().all()
    assert frames["filter_sessions"]["user_id"].notna().all()


def test_unit_change_shrinks_duration_for_one_version() -> None:
    clean = apply_fault(build_events(40), "clean")
    changed = apply_fault(build_events(40), "unit_change_android")
    clean_hit = next(event for event in clean if event["client_version"] == "5.2.0")
    changed_hit = next(event for event in changed if event["client_version"] == "5.2.0")
    assert changed_hit["payload"]["duration_ms"] == clean_hit["payload"]["duration_ms"] / 1000.0


def test_feed_stops_removes_one_version() -> None:
    frames = frames_from_events(build_events(40), fault="feed_stops_ios")
    versions = set(frames["ingest"]["client_version"])
    assert "6.0.1" not in versions
    assert "1.2.0" in versions


def test_type_change_fails_the_numeric_stage() -> None:
    with pytest.raises(TypeError):
        frames_from_events(build_events(40), fault="type_change_android")


def test_unknown_fault_is_rejected() -> None:
    with pytest.raises(ValueError):
        fault_by_id("not-a-fault")


def test_empty_prefix_still_uses_stage_folder() -> None:
    assert object_key("", "aggregate", "run1") == "aggregate/run1.csv"
