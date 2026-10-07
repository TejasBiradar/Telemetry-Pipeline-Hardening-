"""OovRateCheck / TemplateDriftCheck: catch their fault (new vocabulary / a new template),
pass on clean data, and handle a tiny batch / missing baseline."""

from __future__ import annotations

import pandas as pd

from teleguard.checks.base import MIN_SAMPLE_SIZE
from teleguard.drift.baseline import BaselineStore, build_text_baseline
from teleguard.drift.text import OovRateCheck, TemplateDriftCheck
from teleguard.models import BatchContext, Status

CTX = BatchContext(pipeline="p", batch_id="b1")
_REFERENCE = [f"timeout while loading page {i}" for i in range(500)]


def _baselines() -> BaselineStore:
    store = BaselineStore()
    store.set_text("cp", "error_message", None, build_text_baseline(pd.Series(_REFERENCE)))
    return store


class TestOovRateCheck:
    def test_passes_on_familiar_vocabulary(self) -> None:
        df = pd.DataFrame({"error_message": [f"timeout while loading page {i}"
                                            for i in range(MIN_SAMPLE_SIZE)]})
        result = OovRateCheck("cp", "error_message", _baselines(), threshold=0.15).run(df, CTX)[0]
        assert result.status is Status.PASS

    def test_catches_new_vocabulary(self) -> None:
        df = pd.DataFrame({"error_message": [f"upstream dependency unavailable zzzqx {i}"
                                            for i in range(MIN_SAMPLE_SIZE)]})
        result = OovRateCheck("cp", "error_message", _baselines(), threshold=0.15).run(df, CTX)[0]
        assert result.status is Status.FAIL

    def test_handles_tiny_batch(self) -> None:
        df = pd.DataFrame({"error_message": ["timeout"]})
        result = OovRateCheck("cp", "error_message", _baselines()).run(df, CTX)[0]
        assert result.status is Status.INSUFFICIENT_DATA

    def test_no_baseline_yet_is_insufficient_data(self) -> None:
        df = pd.DataFrame({"error_message": ["timeout"] * MIN_SAMPLE_SIZE})
        result = OovRateCheck("cp", "error_message", BaselineStore()).run(df, CTX)[0]
        assert result.status is Status.INSUFFICIENT_DATA


class TestTemplateDriftCheck:
    def test_passes_on_familiar_templates(self) -> None:
        df = pd.DataFrame({"error_message": [f"timeout while loading page {i}"
                                            for i in range(MIN_SAMPLE_SIZE)]})
        result = TemplateDriftCheck("cp", "error_message", _baselines(), threshold=0.30).run(df, CTX)[0]
        assert result.status is Status.PASS

    def test_catches_a_new_template(self) -> None:
        df = pd.DataFrame({"error_message": [f"connection pool exhausted after {i} retries"
                                            for i in range(MIN_SAMPLE_SIZE)]})
        result = TemplateDriftCheck("cp", "error_message", _baselines(), threshold=0.30).run(df, CTX)[0]
        assert result.status is Status.WARN
        assert result.details["new_template_rate"] == 1.0

    def test_missing_field_is_error(self) -> None:
        df = pd.DataFrame({"other": ["x"]})
        result = TemplateDriftCheck("cp", "error_message", _baselines()).run(df, CTX)[0]
        assert result.status is Status.ERROR
