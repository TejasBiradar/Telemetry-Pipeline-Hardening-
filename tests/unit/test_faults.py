"""Each fault: changes exactly what it claims to, only from onset_batch on, only for the
targeted segment, and never mutates the caller's original batches."""

from __future__ import annotations

import random

from teleguard.inject.faults import (
    FaultType,
    inject_clean,
    inject_feed_stops,
    inject_gradual_drift,
    inject_new_nullable,
    inject_text_change,
    inject_type_change,
    inject_unit_change,
    inject_volume_drop,
)


def _event(client_version: str = "v1", duration_ms: float = 1000.0, user_id: str = "u1",
          error_message: str | None = "timeout") -> dict:
    return {"client_version": client_version, "user_id": user_id,
           "payload": {"duration_ms": duration_ms, "error_message": error_message}}


def _batches(n: int = 5, **event_kwargs: object) -> list[list[dict]]:
    return [[_event(**event_kwargs), _event(**{**event_kwargs, "client_version": "other"})]
           for _ in range(n)]


class TestInjectUnitChange:
    def test_changes_the_targeted_field_from_onset_on(self) -> None:
        batches = _batches(duration_ms=1000.0)
        out, _ = inject_unit_change(batches, onset_batch=3, segment="v1", factor=1000.0)
        for i, batch in enumerate(out, start=1):
            v1_event = next(e for e in batch if e["client_version"] == "v1")
            expected = 1.0 if i >= 3 else 1000.0
            assert v1_event["payload"]["duration_ms"] == expected

    def test_leaves_other_segments_untouched(self) -> None:
        batches = _batches(duration_ms=1000.0)
        out, _ = inject_unit_change(batches, onset_batch=1, segment="v1", factor=1000.0)
        other_event = next(e for e in out[0] if e["client_version"] == "other")
        assert other_event["payload"]["duration_ms"] == 1000.0

    def test_does_not_mutate_the_original_batches(self) -> None:
        batches = _batches(duration_ms=1000.0)
        inject_unit_change(batches, onset_batch=1, segment="v1", factor=1000.0)
        assert batches[0][0]["payload"]["duration_ms"] == 1000.0

    def test_records_ground_truth(self) -> None:
        _, injection = inject_unit_change(_batches(), onset_batch=3, segment="v1", factor=1000.0)
        assert injection.fault_type is FaultType.UNIT_CHANGE
        assert injection.segment == "v1"
        assert injection.onset_batch == 3
        assert injection.details["factor"] == 1000.0


class TestInjectFeedStops:
    def test_removes_the_segment_from_onset_on(self) -> None:
        out, _ = inject_feed_stops(_batches(n=5), onset_batch=3, segment="v1")
        for i, batch in enumerate(out, start=1):
            versions = {e["client_version"] for e in batch}
            assert ("v1" in versions) == (i < 3)
            assert "other" in versions  # the other segment is never touched


class TestInjectVolumeDrop:
    def test_reduces_but_does_not_eliminate_the_segment(self) -> None:
        batches = [[_event() for _ in range(100)] for _ in range(5)]
        out, injection = inject_volume_drop(batches, onset_batch=3, segment="v1",
                                            rng=random.Random(1), drop_rate=0.6)
        assert len(out[0]) == 100  # before onset: untouched
        assert 0 < len(out[3]) < 100  # after onset: reduced, not zero
        assert injection.fault_type is FaultType.VOLUME_DROP


class TestInjectNewNullable:
    def test_nulls_a_share_of_the_field_from_onset_on(self) -> None:
        batches = [[_event(user_id="u1") for _ in range(200)] for _ in range(5)]
        out, _ = inject_new_nullable(batches, onset_batch=3, segment="v1",
                                     rng=random.Random(1), field_name="user_id", null_rate=0.5)
        assert all(e["user_id"] is not None for e in out[0])  # before onset
        null_count = sum(1 for e in out[3] if e["user_id"] is None)
        assert 50 < null_count < 150  # roughly half, not all-or-nothing


class TestInjectTypeChange:
    def test_turns_the_field_into_text(self) -> None:
        out, injection = inject_type_change(_batches(duration_ms=1483.0), onset_batch=1, segment="v1")
        v1_event = next(e for e in out[0] if e["client_version"] == "v1")
        assert v1_event["payload"]["duration_ms"] == "1483.0ms"
        assert injection.fault_type is FaultType.TYPE_CHANGE


class TestInjectGradualDrift:
    def test_drift_compounds_batch_by_batch(self) -> None:
        batches = _batches(n=5, duration_ms=100.0)
        out, _ = inject_gradual_drift(batches, onset_batch=2, segment="v1", pct_per_batch=0.10)
        values = [next(e for e in batch if e["client_version"] == "v1")["payload"]["duration_ms"]
                 for batch in out]
        assert values[0] == 100.0  # before onset
        assert values[1] < values[2] < values[3] < values[4]  # strictly increasing after


class TestInjectTextChange:
    def test_replaces_error_messages_with_new_templates(self) -> None:
        batches = [[_event(error_message="timeout") for _ in range(50)] for _ in range(3)]
        out, _ = inject_text_change(batches, onset_batch=2, segment="v1",
                                    rng=random.Random(1), rate=1.0)
        messages = {e["payload"]["error_message"] for e in out[1]}
        assert messages != {"timeout"}
        assert "timeout" not in messages  # rate=1.0: every one replaced


class TestInjectClean:
    def test_is_a_pure_copy_with_a_clean_marker(self) -> None:
        batches = _batches(duration_ms=1000.0)
        out, injection = inject_clean(batches)
        assert out == batches
        assert injection.fault_type is FaultType.CLEAN
        assert injection.onset_batch == len(batches) + 1  # never actually triggers
