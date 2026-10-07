"""AlertManager: dedupes across batches, escalates severity, resolves when the fault clears,
and attaches lineage when a lookup is given."""

from __future__ import annotations

from teleguard.alerts.manager import AlertManager, severity_for_status
from teleguard.models import BatchContext, CheckResult, CheckType, LineageStep, Status

CTX = BatchContext(pipeline="web_analytics", batch_id="b1")


def _fail(field: str = "duration_s", segment: str | None = None, message: str = "bad") -> CheckResult:
    return CheckResult(check=f"range:{field}", check_type=CheckType.RANGE, checkpoint="after_clean",
                       status=Status.FAIL, field=field, segment=segment, message=message)


def test_severity_for_status() -> None:
    assert severity_for_status(Status.FAIL) == "high"
    assert severity_for_status(Status.WARN) == "medium"
    assert severity_for_status(Status.PASS) == "low"


def test_clean_results_produce_no_alerts() -> None:
    mgr = AlertManager()
    passing = CheckResult(check="range:x", check_type=CheckType.RANGE, checkpoint="cp",
                          status=Status.PASS)
    assert mgr.process([passing], CTX) == []
    assert mgr.open_alerts == {}


def test_a_failure_creates_one_alert() -> None:
    mgr = AlertManager()
    alerts = mgr.process([_fail()], CTX)
    assert len(alerts) == 1
    assert alerts[0].severity == "high"
    assert alerts[0].root_field == "duration_s"


def test_the_same_failing_field_does_not_duplicate_across_batches() -> None:
    mgr = AlertManager()
    mgr.process([_fail()], CTX)
    mgr.process([_fail()], BatchContext(pipeline="web_analytics", batch_id="b2"))
    assert len(mgr.open_alerts) == 1  # still one alert, not two


def test_different_segments_in_the_same_checkpoint_produce_separate_alerts() -> None:
    # Realistic shape: one guard.check() call for one checkpoint covers every segment in
    # that batch, so both segments' results arrive in a single process() call together.
    mgr = AlertManager()
    mgr.process([_fail(segment="ios"), _fail(segment="android")], CTX)
    assert len(mgr.open_alerts) == 2


def test_an_alert_from_one_checkpoint_is_not_resolved_by_checking_another() -> None:
    # Regression test: guard.check() is called once per checkpoint, so a process() call
    # about "after_aggregate" must not clear an open alert that belongs to "after_clean".
    mgr = AlertManager()
    after_clean_failure = CheckResult(check="range:duration_s", check_type=CheckType.RANGE,
                                      checkpoint="after_clean", status=Status.FAIL,
                                      field="duration_s", message="bad")
    mgr.process([after_clean_failure], CTX)
    assert len(mgr.open_alerts) == 1

    unrelated_pass = CheckResult(check="range:error_rate", check_type=CheckType.RANGE,
                                 checkpoint="after_aggregate", status=Status.PASS,
                                 field="error_rate")
    mgr.process([unrelated_pass], CTX)

    assert len(mgr.open_alerts) == 1  # the after_clean alert must still be open


def test_a_resolved_fault_drops_its_open_alert() -> None:
    mgr = AlertManager()
    mgr.process([_fail()], CTX)
    assert len(mgr.open_alerts) == 1
    passing = CheckResult(check="range:duration_s", check_type=CheckType.RANGE,
                          checkpoint="after_clean", status=Status.PASS, field="duration_s")
    mgr.process([passing], BatchContext(pipeline="web_analytics", batch_id="b2"))
    assert mgr.open_alerts == {}


class _FakeLineage:
    def trace(self, field: str) -> list[LineageStep]:
        return [LineageStep(node_id=f"field:{field}", node_type="field", label=field)]

    def affected_outputs(self, field: str) -> list[str]:
        return ["avg_duration_s", "p95_duration_s"]


def test_lineage_is_attached_when_a_lookup_is_given() -> None:
    mgr = AlertManager()
    alerts = mgr.process([_fail()], CTX, lineage=_FakeLineage())
    assert alerts[0].affected_outputs == ["avg_duration_s", "p95_duration_s"]
    assert alerts[0].lineage[0].node_id == "field:duration_s"


def test_no_lineage_lookup_leaves_lineage_empty() -> None:
    mgr = AlertManager()
    alerts = mgr.process([_fail()], CTX)
    assert alerts[0].lineage == []
    assert alerts[0].affected_outputs == []
