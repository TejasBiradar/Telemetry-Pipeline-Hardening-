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


def test_lists_discovered_pipelines(client: TestClient) -> None:
    data = client.get("/pipelines").json()
    ids = {p["id"] for p in data["pipelines"]}
    assert ids == {"web_analytics", "user_behavior", "payment_processing"}
    assert data["active"] == "web_analytics"


def test_selecting_user_behavior_returns_its_own_graph(client: TestClient) -> None:
    assert client.put("/pipelines/user_behavior/select").status_code == 200
    graph = client.get("/pipeline/graph").json()
    assert graph["stages"] == ["ingest", "filter_sessions", "aggregate"]
    # Restore default so later tests keep using web_analytics baselines/scenarios.
    assert client.put("/pipelines/web_analytics/select").status_code == 200


def test_pipeline_graph_has_the_real_web_analytics_stages(client: TestClient) -> None:
    graph = client.get("/pipeline/graph").json()
    stage_labels = [n["label"] for n in graph["nodes"] if n["type"] == "stage"]
    assert stage_labels == ["ingest", "clean", "enrich", "aggregate"]


def test_guarantees_lists_the_real_findings(client: TestClient) -> None:
    guarantees = client.get("/pipeline/guarantees").json()
    assert len(guarantees) == 15  # matches GUARANTEES.md as of this review
    # Statuses can be pending, confirmed, or rejected depending on prior test runs
    statuses = {g["status"] for g in guarantees}
    assert statuses.issubset({"pending", "confirmed", "rejected"})
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


def test_scenario_run_returns_a_per_batch_timeline_and_alert_timing(client: TestClient) -> None:
    result = client.post("/scenarios/unit_change_android/run").json()
    batches = result["batches"]
    assert [b["batch"] for b in batches] == list(range(1, len(batches) + 1))
    onset = result["onset_batch"]
    assert all(b["failed"] == 0 for b in batches if b["batch"] < onset)
    assert any(b["failed"] > 0 for b in batches if b["batch"] >= onset)
    alert = result["alerts"][0]
    assert alert["first_batch"] is not None
    assert alert["root_field"]


def test_clean_scenario_timeline_has_no_failures(client: TestClient) -> None:
    result = client.post("/scenarios/clean/run").json()
    assert result["batches"]
    assert all(b["failed"] == 0 for b in result["batches"])


def test_can_confirm_a_guarantee(client: TestClient) -> None:
    guarantees = client.get("/pipeline/guarantees").json()
    assert len(guarantees) > 0
    # Find a pending one, or just use the first
    g = next((x for x in guarantees if x["status"] == "pending"), guarantees[0])
    # Confirm it
    response = client.post(f"/pipeline/guarantees/{g['id']}/decision", json={"status": "confirmed"})
    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == "confirmed"
    # Verify it persisted
    guarantees2 = client.get("/pipeline/guarantees").json()
    g2 = next((x for x in guarantees2 if x["id"] == g["id"]), None)
    assert g2 is not None
    assert g2["status"] == "confirmed"


def test_can_reject_a_guarantee(client: TestClient) -> None:
    guarantees = client.get("/pipeline/guarantees").json()
    pending = next((g for g in guarantees if g["status"] == "pending"), None)
    assert pending is not None
    # Reject it
    response = client.post(f"/pipeline/guarantees/{pending['id']}/decision", json={"status": "rejected"})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_reject_unknown_guarantee_is_404(client: TestClient) -> None:
    response = client.post("/pipeline/guarantees/no_such_id/decision", json={"status": "confirmed"})
    assert response.status_code == 404


def test_invalid_decision_status_is_400(client: TestClient) -> None:
    guarantees = client.get("/pipeline/guarantees").json()
    response = client.post(f"/pipeline/guarantees/{guarantees[0]['id']}/decision", json={"status": "invalid"})
    assert response.status_code == 400
