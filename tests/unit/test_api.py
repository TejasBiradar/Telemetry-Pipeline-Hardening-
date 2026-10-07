"""API tests against the real app (startup builds the real baseline store, ~15-20s — the
client fixture is module-scoped so that only happens once)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_health_is_ok_once_started(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_pipeline_graph_has_the_real_web_analytics_stages(client: TestClient) -> None:
    graph = client.get("/pipeline/graph").json()
    stage_labels = [n["label"] for n in graph["nodes"] if n["type"] == "stage"]
    assert stage_labels == ["ingest", "clean", "enrich", "aggregate"]


def test_guarantees_lists_the_real_pending_findings(client: TestClient) -> None:
    guarantees = client.get("/pipeline/guarantees").json()
    assert len(guarantees) == 15  # matches GUARANTEES.md as of this review
    assert all(g["status"] == "pending" for g in guarantees)  # none reviewed yet
    kinds = {g["kind"] for g in guarantees}
    assert "unit_conversion" in kinds


def test_scenarios_lists_all_eight(client: TestClient) -> None:
    scenarios = client.get("/scenarios").json()
    assert len(scenarios) == 8
    names = {s["name"] for s in scenarios}
    assert "unit_change_android" in names
    assert "clean" in names


def test_running_an_unknown_scenario_is_a_404(client: TestClient) -> None:
    response = client.post("/scenarios/no_such_scenario/run")
    assert response.status_code == 404


def test_running_unit_change_detects_it_and_returns_a_real_alert(client: TestClient) -> None:
    result = client.post("/scenarios/unit_change_android/run").json()
    assert result["detected"] is True
    assert result["lag_batches"] == 0
    assert any(a["segment"] == "5.2.0" for a in result["alerts"])


def test_running_clean_produces_no_detection(client: TestClient) -> None:
    result = client.post("/scenarios/clean/run").json()
    assert result["detected"] is False


def test_evaluation_is_cached_across_calls(client: TestClient) -> None:
    first = client.get("/evaluation")
    assert first.status_code == 200
    summaries = {s["system"]: s for s in first.json()}
    assert set(summaries) == {"B0", "B1", "ours"}
    assert summaries["ours"]["recall"] >= 0.75
    assert summaries["B0"]["recall"] == 0.0

    # second call must reuse the cache, not take another ~100s
    second = client.get("/evaluation")
    assert second.json() == first.json()
