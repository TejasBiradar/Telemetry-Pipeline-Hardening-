"""Confirming a stage must not backfill historical stage files into Results."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from teleguard.agent.results_store import AgentRun, append_run, list_runs
from teleguard.agent.seed_seen import (
    baseline_stage_outputs,
    newly_confirmed_stages,
    seed_existing_outputs,
    watch_baseline_key,
)
from teleguard.agent.seen_state import load_seen
from teleguard.onboard.code import CodeOnboardRecord, set_stage_decision
from teleguard.onboard.output_store import parse_output_store


def _record(**overrides: Any) -> CodeOnboardRecord:
    base = CodeOnboardRecord(
        pipeline_id="pipe-1",
        name="demo",
        description="",
        entry="run.run",
        adapter="python_pandas",
        source_path="/tmp/demo",
        git_url="",
        git_ref="",
        source_subdir="",
        analyzed_at="2026-01-01T00:00:00Z",
        stages=["ingest", "clean", "enrich"],
        checkpoints=[],
        findings=[],
        graph={"nodes": [], "edges": []},
        stage_ids=["s1", "s2", "s3"],
        stage_status={"ingest": "pending", "clean": "pending", "enrich": "pending"},
        guarantee_status={},
        output_store={
            "type": "minio",
            "endpoint": "http://minio:9000",
            "bucket": "demo",
            "prefix": "demo/outputs",
            "secure": False,
            "access_key": "x",
            "secret_key": "y",
            "stages": [
                {"stage": "ingest", "location": "demo/outputs/ingest/"},
                {"stage": "clean", "location": "demo/outputs/clean/"},
                {"stage": "enrich", "location": "demo/outputs/enrich/"},
            ],
        },
    )
    return replace(base, **overrides) if overrides else base


def test_newly_confirmed_stages_detects_flip() -> None:
    before = _record()
    after = set_stage_decision(before, "enrich", "confirmed")
    assert newly_confirmed_stages(before, after) == ["enrich"]
    assert newly_confirmed_stages(after, after) == []


def test_baseline_marks_history_and_clears_stored_runs(tmp_path: Path) -> None:
    record = set_stage_decision(_record(), "enrich", "confirmed")
    old_key = "demo/outputs/enrich/20260601T000000Z-old.csv"
    append_run(
        AgentRun(
            pipeline_id="pipe-1",
            stage="enrich",
            checkpoint="after_enrich",
            object_key=old_key,
            batch_id=old_key,
            observed_at="2026-06-01T00:00:00Z",
            results=[],
            failed=0,
            passed=1,
        ),
        store_root=tmp_path,
    )

    class FakeObj:
        def __init__(self, key: str) -> None:
            self.key = key

    with patch(
        "teleguard.agent.seed_seen.list_objects",
        return_value=[FakeObj(old_key)],
    ):
        took = baseline_stage_outputs(
            "pipe-1",
            parse_output_store(record.output_store),  # type: ignore[arg-type]
            stage="enrich",
            location="demo/outputs/enrich/",
            store_root=tmp_path,
            force=False,
        )

    assert took is True
    seen = load_seen("pipe-1", store_root=tmp_path)
    assert old_key in seen
    assert watch_baseline_key("enrich") in seen
    assert list_runs("pipe-1", store_root=tmp_path) == []
    # Second call does not baseline again.
    with patch("teleguard.agent.seed_seen.list_objects", return_value=[FakeObj(old_key)]):
        assert (
            baseline_stage_outputs(
                "pipe-1",
                parse_output_store(record.output_store),  # type: ignore[arg-type]
                stage="enrich",
                location="demo/outputs/enrich/",
                store_root=tmp_path,
                force=False,
            )
            is False
        )


def test_seed_skips_when_no_output_store(tmp_path: Path) -> None:
    record = set_stage_decision(replace(_record(), output_store=None), "ingest", "confirmed")
    assert seed_existing_outputs(record, store_root=tmp_path) == 0


def test_delete_runs_for_stages_removes_unwatched_history(tmp_path: Path) -> None:
    from teleguard.agent.results_store import delete_runs_for_stages

    for stage, key in (
        ("enrich", "demo/outputs/enrich/a.csv"),
        ("reconcile", "demo/outputs/reconcile/a.csv"),
    ):
        append_run(
            AgentRun(
                pipeline_id="pipe-1",
                stage=stage,
                checkpoint=f"after_{stage}",
                object_key=key,
                batch_id=key,
                observed_at="2026-06-01T00:00:00Z",
                results=[],
                failed=0,
                passed=1,
            ),
            store_root=tmp_path,
        )
    removed = delete_runs_for_stages("pipe-1", ["reconcile"], store_root=tmp_path)
    assert removed == 1
    left = list_runs("pipe-1", store_root=tmp_path)
    assert len(left) == 1
    assert left[0].stage == "enrich"
