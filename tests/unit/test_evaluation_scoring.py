"""score_scenario's matching rule, tested directly against hand-built ScenarioRun objects —
fast, no real pipeline run needed. The slow end-to-end check lives in
test_evaluation_integration.py."""

from __future__ import annotations

from teleguard.evaluate.engine import ScenarioRun, score_scenario
from teleguard.inject.faults import FaultType, Injection
from teleguard.models import Alert


def _run(injection: Injection, alerts: dict[str, Alert], first_batch: dict[str, int]) -> ScenarioRun:
    return ScenarioRun("s", injection, results_by_batch=[], alerts=alerts,
                      alert_first_batch=first_batch, crashed_at_batch=None)


def test_an_alert_on_the_right_segment_within_the_window_is_a_true_positive() -> None:
    injection = Injection("i1", FaultType.UNIT_CHANGE, "duration_ms", "v1", onset_batch=4)
    alert = Alert(alert_id="a1", pipeline="p", batch_id="batch_0005", severity="high",
                 message="m", segment="v1")
    score = score_scenario(_run(injection, {"a1": alert}, {"a1": 5}), window=5)
    assert score.detected
    assert score.lag_batches == 1
    assert score.true_positive_alerts == 1
    assert score.false_positive_alerts == 0


def test_an_alert_outside_the_window_is_a_false_positive() -> None:
    injection = Injection("i1", FaultType.UNIT_CHANGE, "duration_ms", "v1", onset_batch=4)
    alert = Alert(alert_id="a1", pipeline="p", batch_id="batch_0012", severity="high",
                 message="m", segment="v1")
    score = score_scenario(_run(injection, {"a1": alert}, {"a1": 12}), window=5)
    assert not score.detected
    assert score.false_positive_alerts == 1


def test_an_alert_before_onset_is_a_false_positive() -> None:
    injection = Injection("i1", FaultType.UNIT_CHANGE, "duration_ms", "v1", onset_batch=4)
    alert = Alert(alert_id="a1", pipeline="p", batch_id="batch_0002", severity="high",
                 message="m", segment="v1")
    score = score_scenario(_run(injection, {"a1": alert}, {"a1": 2}), window=5)
    assert not score.detected
    assert score.false_positive_alerts == 1


def test_an_alert_on_the_wrong_segment_is_a_false_positive() -> None:
    injection = Injection("i1", FaultType.UNIT_CHANGE, "duration_ms", "v1", onset_batch=4)
    alert = Alert(alert_id="a1", pipeline="p", batch_id="batch_0004", severity="high",
                 message="m", segment="v2")
    score = score_scenario(_run(injection, {"a1": alert}, {"a1": 4}), window=5)
    assert not score.detected
    assert score.false_positive_alerts == 1


def test_a_segment_less_alert_can_still_match_a_specific_injection() -> None:
    # Whole-batch checks (schema, whole-batch volume) never set `segment`, but can still be
    # the thing that genuinely caught a segment-specific fault.
    injection = Injection("i1", FaultType.TYPE_CHANGE, "duration_ms", "v1", onset_batch=4)
    alert = Alert(alert_id="a1", pipeline="p", batch_id="batch_0004", severity="high",
                 message="m", segment=None)
    score = score_scenario(_run(injection, {"a1": alert}, {"a1": 4}), window=5)
    assert score.detected
    assert score.true_positive_alerts == 1


def test_every_alert_on_a_clean_scenario_is_a_false_positive() -> None:
    injection = Injection("clean", FaultType.CLEAN, None, None, onset_batch=11)
    alert = Alert(alert_id="a1", pipeline="p", batch_id="batch_0003", severity="high",
                 message="m", segment="v1")
    score = score_scenario(_run(injection, {"a1": alert}, {"a1": 3}), window=5)
    assert not score.detected
    assert score.false_positive_alerts == 1
    assert score.true_positive_alerts == 0


def test_no_alerts_at_all_means_not_detected_with_no_false_positives() -> None:
    injection = Injection("i1", FaultType.UNIT_CHANGE, "duration_ms", "v1", onset_batch=4)
    score = score_scenario(_run(injection, {}, {}), window=5)
    assert not score.detected
    assert score.false_positive_alerts == 0
    assert score.lag_batches is None


def test_lag_picks_the_earliest_matching_alert() -> None:
    injection = Injection("i1", FaultType.UNIT_CHANGE, "duration_ms", "v1", onset_batch=4)
    early = Alert(alert_id="a1", pipeline="p", batch_id="batch_0005", severity="high",
                 message="m", segment="v1")
    late = Alert(alert_id="a2", pipeline="p", batch_id="batch_0007", severity="high",
                message="m", segment="v1")
    score = score_scenario(_run(injection, {"a1": early, "a2": late}, {"a2": 7, "a1": 5}), window=5)
    assert score.lag_batches == 1
    assert score.true_positive_alerts == 2
