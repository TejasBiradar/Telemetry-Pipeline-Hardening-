"""SegmentVolumeCheck: catches its fault (a segment going silent or dropping sharply),
passes on clean data, and handles having no baseline yet."""

from __future__ import annotations

import pandas as pd

from teleguard.checks.segment_volume import SegmentVolumeCheck
from teleguard.drift.baseline import BaselineStore, build_segment_volume_baselines
from teleguard.models import BatchContext, Status

CTX = BatchContext(pipeline="p", batch_id="b4", segment_column="client_version")


def _baselines() -> BaselineStore:
    # Three "normal" batches: v1 ~100 rows, v2 ~50 rows, every batch.
    per_batch = [
        pd.DataFrame({"client_version": ["v1"] * 100 + ["v2"] * 50}),
        pd.DataFrame({"client_version": ["v1"] * 98 + ["v2"] * 52}),
        pd.DataFrame({"client_version": ["v1"] * 102 + ["v2"] * 49}),
    ]
    store = BaselineStore()
    for segment, baseline in build_segment_volume_baselines(per_batch, "client_version").items():
        store.set_segment_volume("after_clean", segment, baseline)
    return store


def test_passes_when_every_segment_is_near_its_usual_volume() -> None:
    df = pd.DataFrame({"client_version": ["v1"] * 100 + ["v2"] * 50})
    results = SegmentVolumeCheck("after_clean", _baselines()).run(df, CTX)
    assert all(r.status is Status.PASS for r in results)


def test_catches_a_segment_going_completely_silent() -> None:
    df = pd.DataFrame({"client_version": ["v1"] * 100})  # v2 never appears
    results = {r.segment: r for r in SegmentVolumeCheck("after_clean", _baselines()).run(df, CTX)}
    assert results["v2"].status is Status.FAIL
    assert "silent" in results["v2"].message
    assert results["v1"].status is Status.PASS


def test_catches_a_partial_volume_drop() -> None:
    df = pd.DataFrame({"client_version": ["v1"] * 100 + ["v2"] * 10})  # v2 down from ~50 to 10
    results = {r.segment: r for r in SegmentVolumeCheck("after_clean", _baselines()).run(df, CTX)}
    assert results["v2"].status is Status.FAIL


def test_no_baseline_yet_is_insufficient_data() -> None:
    df = pd.DataFrame({"client_version": ["v1"] * 10})
    result = SegmentVolumeCheck("after_clean", BaselineStore()).run(df, CTX)[0]
    assert result.status is Status.INSUFFICIENT_DATA


def test_missing_segment_column_is_error() -> None:
    df = pd.DataFrame({"other": [1]})
    result = SegmentVolumeCheck("after_clean", _baselines()).run(df, CTX)[0]
    assert result.status is Status.ERROR


def test_build_segment_volume_baselines_records_zero_for_absent_batches() -> None:
    per_batch = [
        pd.DataFrame({"seg": ["a"] * 10, "x": 1}),
        pd.DataFrame({"seg": ["b"] * 5, "x": 1}),  # "a" (known since batch 1) absent this batch
    ]
    baselines = build_segment_volume_baselines(per_batch, "seg")
    assert baselines["a"].batch_counts == (10, 0)
    # "b" wasn't known to exist until batch 2, so it has no pre-existence history to backfill.
    assert baselines["b"].batch_counts == (5,)
