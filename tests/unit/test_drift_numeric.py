"""PsiCheck / KsCheck: catch their fault (a shifted distribution), pass on clean data, and
handle a tiny batch / missing baseline."""

from __future__ import annotations

import pandas as pd

from teleguard.checks.base import MIN_SAMPLE_SIZE
from teleguard.drift.baseline import BaselineStore, build_numeric_baseline
from teleguard.drift.numeric import KsCheck, PsiCheck
from teleguard.models import BatchContext, Status

CTX = BatchContext(pipeline="p", batch_id="b1")
_REFERENCE = [3.0 + (i % 11) * 0.2 for i in range(500)]  # a stable, slightly-varying reference


def _baselines() -> BaselineStore:
    store = BaselineStore()
    store.set_numeric("cp", "duration_s", None, build_numeric_baseline(pd.Series(_REFERENCE)))
    return store


class TestPsiCheck:
    def test_passes_on_data_matching_the_baseline(self) -> None:
        df = pd.DataFrame({"duration_s": [3.0 + (i % 11) * 0.2 for i in range(MIN_SAMPLE_SIZE)]})
        result = PsiCheck("cp", "duration_s", _baselines(), threshold=0.10).run(df, CTX)[0]
        assert result.status is Status.PASS

    def test_catches_a_shifted_distribution(self) -> None:
        df = pd.DataFrame({"duration_s": [30.0 + (i % 11) * 0.2 for i in range(MIN_SAMPLE_SIZE)]})
        result = PsiCheck("cp", "duration_s", _baselines(), threshold=0.10).run(df, CTX)[0]
        assert result.status is Status.FAIL

    def test_handles_tiny_batch(self) -> None:
        df = pd.DataFrame({"duration_s": [3.0, 3.1]})
        result = PsiCheck("cp", "duration_s", _baselines()).run(df, CTX)[0]
        assert result.status is Status.INSUFFICIENT_DATA

    def test_no_baseline_yet_is_insufficient_data(self) -> None:
        df = pd.DataFrame({"duration_s": [3.0] * MIN_SAMPLE_SIZE})
        result = PsiCheck("cp", "duration_s", BaselineStore()).run(df, CTX)[0]
        assert result.status is Status.INSUFFICIENT_DATA


class TestKsCheck:
    def test_passes_on_data_matching_the_baseline(self) -> None:
        df = pd.DataFrame({"duration_s": [3.0 + (i % 11) * 0.2 for i in range(MIN_SAMPLE_SIZE)]})
        result = KsCheck("cp", "duration_s", _baselines()).run(df, CTX)[0]
        assert result.status is Status.PASS

    def test_catches_a_shifted_distribution(self) -> None:
        df = pd.DataFrame({"duration_s": [30.0 + (i % 11) * 0.2 for i in range(MIN_SAMPLE_SIZE)]})
        result = KsCheck("cp", "duration_s", _baselines()).run(df, CTX)[0]
        assert result.status is Status.FAIL

    def test_missing_field_is_error(self) -> None:
        df = pd.DataFrame({"other": [1.0]})
        result = KsCheck("cp", "duration_s", _baselines()).run(df, CTX)[0]
        assert result.status is Status.ERROR
