"""UnitConsistencyCheck: catches its fault (a clean unit flip), passes on clean data, and
handles a tiny batch / missing baseline."""

from __future__ import annotations

import pandas as pd

from teleguard.checks.base import MIN_SAMPLE_SIZE
from teleguard.checks.unit import UnitConsistencyCheck
from teleguard.drift.baseline import BaselineStore, build_numeric_baseline
from teleguard.models import BatchContext, Status

CTX = BatchContext(pipeline="p", batch_id="b1")


def _baselines(values: list[float]) -> BaselineStore:
    store = BaselineStore()
    store.set_numeric("cp", "duration_s", None, build_numeric_baseline(pd.Series(values)))
    return store


def test_passes_on_clean_data() -> None:
    reference = [3.0 + (i % 5) * 0.1 for i in range(MIN_SAMPLE_SIZE)]
    baselines = _baselines(reference)
    current = pd.DataFrame({"duration_s": [3.0 + (i % 5) * 0.1 for i in range(MIN_SAMPLE_SIZE)]})
    result = UnitConsistencyCheck("cp", "duration_s", baselines).run(current, CTX)[0]
    assert result.status is Status.PASS


def test_catches_a_1000x_unit_flip() -> None:
    reference = [0.3 + (i % 5) * 0.01 for i in range(MIN_SAMPLE_SIZE)]  # seconds
    baselines = _baselines(reference)
    current = pd.DataFrame({"duration_s": [300.0 + (i % 5) for i in range(MIN_SAMPLE_SIZE)]})  # ms mislabeled as s
    result = UnitConsistencyCheck("cp", "duration_s", baselines).run(current, CTX)[0]
    assert result.status is Status.FAIL
    assert "unit change" in result.message


def test_no_baseline_yet_is_insufficient_data() -> None:
    baselines = BaselineStore()
    current = pd.DataFrame({"duration_s": [1.0] * MIN_SAMPLE_SIZE})
    result = UnitConsistencyCheck("cp", "duration_s", baselines).run(current, CTX)[0]
    assert result.status is Status.INSUFFICIENT_DATA


def test_handles_tiny_batch() -> None:
    baselines = _baselines([1.0] * MIN_SAMPLE_SIZE)
    current = pd.DataFrame({"duration_s": [1.0, 2.0]})
    result = UnitConsistencyCheck("cp", "duration_s", baselines).run(current, CTX)[0]
    assert result.status is Status.INSUFFICIENT_DATA


def test_missing_field_is_error() -> None:
    baselines = _baselines([1.0] * MIN_SAMPLE_SIZE)
    current = pd.DataFrame({"other": [1.0]})
    result = UnitConsistencyCheck("cp", "duration_s", baselines).run(current, CTX)[0]
    assert result.status is Status.ERROR
