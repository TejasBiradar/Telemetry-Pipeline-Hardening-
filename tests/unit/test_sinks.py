from __future__ import annotations

from teleguard.drift.baseline import BaselineStore
from teleguard.models import Alert, CheckResult, CheckType, Status
from teleguard.sinks import MemorySink


def test_memory_sink_accumulates_results() -> None:
    sink = MemorySink()
    r = CheckResult(check="x", check_type=CheckType.SCHEMA, checkpoint="cp", status=Status.PASS)
    sink.record_results([r])
    sink.record_results([r])
    assert len(sink.results) == 2


def test_memory_sink_dedupes_alerts_by_alert_id() -> None:
    sink = MemorySink()
    first = Alert(alert_id="a1", pipeline="p", batch_id="b1", severity="high", message="m1")
    updated = Alert(alert_id="a1", pipeline="p", batch_id="b2", severity="medium", message="m2")
    sink.record_alerts([first])
    sink.record_alerts([updated])
    assert len(sink.alerts) == 1
    assert sink.alerts["a1"].message == "m2"


def test_memory_sink_record_baselines_is_a_no_op() -> None:
    sink = MemorySink()
    sink.record_baselines("cp", BaselineStore())  # must not raise
