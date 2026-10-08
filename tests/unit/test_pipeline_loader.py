"""Discovery + on-the-fly code-graph generation for multiple pipelines."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.state import build_state
from teleguard.pipeline_loader import build_registry, discover_pipeline_dirs, load_pipeline

ROOT = Path(__file__).resolve().parents[2]
PIPELINES = ROOT / "pipelines"


def test_discovers_all_real_pipelines() -> None:
    ids = {p.name for p in discover_pipeline_dirs(PIPELINES)}
    assert ids == {"web_analytics", "user_behavior", "payment_processing"}


def test_each_pipeline_gets_a_non_empty_on_the_fly_graph() -> None:
    registry = build_registry(PIPELINES)
    for pipeline_id, meta in registry.pipelines.items():
        graph = meta.graph()
        assert graph["nodes"], f"{pipeline_id} has no nodes"
        assert graph["edges"], f"{pipeline_id} has no edges"
        assert meta.stages(), f"{pipeline_id} has no stages"
        assert meta.findings_json, f"{pipeline_id} should surface findings from analysis"


def test_pipelines_have_distinct_stage_graphs() -> None:
    registry = build_registry(PIPELINES)
    web = registry.get("web_analytics")
    user = registry.get("user_behavior")
    pay = registry.get("payment_processing")
    assert web is not None and user is not None and pay is not None
    assert web.stages() == ["ingest", "clean", "enrich", "aggregate"]
    assert user.stages() == ["ingest", "filter_sessions", "aggregate"]
    assert pay.stages() == ["ingest", "clean", "enrich", "reconcile"]


def test_default_active_comes_from_pipeline_yaml() -> None:
    registry = build_registry(PIPELINES)
    assert registry.active_pipeline_id == "web_analytics"


def test_api_state_lists_three_pipelines_without_dummy_graphs() -> None:
    state = build_state(PIPELINES)
    listed = state.registry.to_json()
    assert {p["id"] for p in listed["pipelines"]} == {
        "web_analytics",
        "user_behavior",
        "payment_processing",
    }
    # Dummy registry entries reused web_analytics' module; real ones must not.
    modules = {
        p.id: id(getattr(p, "_legacy_module", None))
        for p in state.registry.list_all()
    }
    assert len(set(modules.values())) == 3


def test_load_pipeline_does_not_require_cached_graph_json(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "run.py").write_text(
        "import pandas as pd\n"
        "def ingest(df):\n"
        "    return df\n"
        "def tidy(df):\n"
        '    df = df[df["x"].notna()].copy()\n'
        '    df["y"] = df["x"] / 1000.0\n'
        "    return df\n"
        "def run(df):\n"
        "    df = ingest(df)\n"
        "    return tidy(df)\n"
    )
    (tmp_path / "pipeline.yaml").write_text(
        "name: toy\nentry: run.run\nsource_dir: src\n"
    )
    meta = load_pipeline(tmp_path)
    assert meta.stages() == ["ingest", "tidy"]
    assert any(f["kind"] == "unit_conversion" for f in meta.findings_json)


@pytest.mark.parametrize(
    "pipeline_id,expected_stage",
    [
        ("user_behavior", "filter_sessions"),
        ("payment_processing", "reconcile"),
    ],
)
def test_selecting_demo_pipeline_exposes_its_own_graph(
    pipeline_id: str, expected_stage: str
) -> None:
    state = build_state(PIPELINES, active_id=pipeline_id)
    active = state.active_pipeline()
    assert active is not None
    assert expected_stage in active.stages()
    labels = {n["label"] for n in active.graph()["nodes"] if n["type"] == "stage"}
    assert expected_stage in labels
