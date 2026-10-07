"""Each gate: catches its fault, passes on clean data, handles a tiny/empty batch
(CLAUDE.md's bar for a check being "done")."""

from __future__ import annotations

import pandas as pd

from teleguard.checks.base import MIN_SAMPLE_SIZE
from teleguard.checks.gates import (
    CardinalityCheck,
    KeySetCheck,
    NullRateCheck,
    RangeCheck,
    SchemaCheck,
    VolumeCheck,
)
from teleguard.models import BatchContext, Status

CTX = BatchContext(pipeline="p", batch_id="b1")


def _df(n: int, **cols: object) -> pd.DataFrame:
    return pd.DataFrame({k: (v if isinstance(v, list) else [v] * n) for k, v in cols.items()})


class TestSchemaCheck:
    def test_passes_on_clean_data(self) -> None:
        df = pd.DataFrame({"user_id": ["u1", "u2"]})
        result = SchemaCheck("cp", "user_id", "object").run(df, CTX)[0]
        assert result.status is Status.PASS

    def test_catches_missing_field(self) -> None:
        df = pd.DataFrame({"other": [1]})
        result = SchemaCheck("cp", "user_id").run(df, CTX)[0]
        assert result.status is Status.FAIL

    def test_catches_wrong_dtype(self) -> None:
        df = pd.DataFrame({"user_id": [1, 2]})
        result = SchemaCheck("cp", "user_id", "object").run(df, CTX)[0]
        assert result.status is Status.FAIL

    def test_handles_empty_batch(self) -> None:
        df = pd.DataFrame({"user_id": pd.Series([], dtype="object")})
        result = SchemaCheck("cp", "user_id", "object").run(df, CTX)[0]
        assert result.status is Status.PASS


class TestNullRateCheck:
    def test_passes_on_clean_data(self) -> None:
        df = _df(MIN_SAMPLE_SIZE, user_id=[f"u{i}" for i in range(MIN_SAMPLE_SIZE)])
        result = NullRateCheck("cp", "user_id", max_null_rate=0.05).run(df, CTX)[0]
        assert result.status is Status.PASS

    def test_catches_high_null_rate(self) -> None:
        values = [None] * 20 + [f"u{i}" for i in range(MIN_SAMPLE_SIZE - 20)]
        df = _df(MIN_SAMPLE_SIZE, user_id=values)
        result = NullRateCheck("cp", "user_id", max_null_rate=0.05).run(df, CTX)[0]
        assert result.status is Status.FAIL

    def test_handles_tiny_batch_as_insufficient_data(self) -> None:
        df = _df(3, user_id=["u1", None, "u3"])
        result = NullRateCheck("cp", "user_id", max_null_rate=0.05).run(df, CTX)[0]
        assert result.status is Status.INSUFFICIENT_DATA

    def test_missing_field_is_error(self) -> None:
        df = pd.DataFrame({"other": [1]})
        result = NullRateCheck("cp", "user_id", max_null_rate=0.05).run(df, CTX)[0]
        assert result.status is Status.ERROR


class TestRangeCheck:
    def test_passes_on_clean_data(self) -> None:
        df = _df(MIN_SAMPLE_SIZE, duration_s=[float(i % 100) for i in range(MIN_SAMPLE_SIZE)])
        result = RangeCheck("cp", "duration_s", min=0, max=300).run(df, CTX)[0]
        assert result.status is Status.PASS

    def test_catches_out_of_range_values(self) -> None:
        df = _df(MIN_SAMPLE_SIZE, duration_s=[500.0] * MIN_SAMPLE_SIZE)
        result = RangeCheck("cp", "duration_s", min=0, max=300).run(df, CTX)[0]
        assert result.status is Status.FAIL

    def test_handles_tiny_batch(self) -> None:
        df = _df(2, duration_s=[1.0, 2.0])
        result = RangeCheck("cp", "duration_s", min=0, max=300).run(df, CTX)[0]
        assert result.status is Status.INSUFFICIENT_DATA


class TestVolumeCheck:
    def test_passes_within_band(self) -> None:
        df = _df(100, x=1)
        result = VolumeCheck("cp", min_rows=50, max_rows=200).run(df, CTX)[0]
        assert result.status is Status.PASS

    def test_catches_too_few_rows(self) -> None:
        df = _df(5, x=1)
        result = VolumeCheck("cp", min_rows=50, max_rows=200).run(df, CTX)[0]
        assert result.status is Status.FAIL

    def test_handles_empty_batch(self) -> None:
        df = pd.DataFrame({"x": pd.Series([], dtype="int64")})
        result = VolumeCheck("cp", min_rows=50, max_rows=200).run(df, CTX)[0]
        assert result.status is Status.FAIL


class TestKeySetCheck:
    def test_passes_on_clean_data(self) -> None:
        df = pd.DataFrame({"country": ["US", "GB", "US"]})
        result = KeySetCheck("cp", "country", allowed=["US", "GB"]).run(df, CTX)[0]
        assert result.status is Status.PASS

    def test_catches_unexpected_value(self) -> None:
        df = pd.DataFrame({"country": ["US", "FR"]})
        result = KeySetCheck("cp", "country", allowed=["US", "GB"]).run(df, CTX)[0]
        assert result.status is Status.WARN
        assert "FR" in result.message

    def test_handles_empty_batch(self) -> None:
        df = pd.DataFrame({"country": pd.Series([], dtype="object")})
        result = KeySetCheck("cp", "country", allowed=["US"]).run(df, CTX)[0]
        assert result.status is Status.PASS


class TestCardinalityCheck:
    def test_passes_on_clean_data(self) -> None:
        df = pd.DataFrame({"client_version": ["1.0", "1.0", "1.1"]})
        result = CardinalityCheck("cp", "client_version", max_distinct=3).run(df, CTX)[0]
        assert result.status is Status.PASS

    def test_catches_too_many_distinct_values(self) -> None:
        df = pd.DataFrame({"client_version": [str(i) for i in range(10)]})
        result = CardinalityCheck("cp", "client_version", max_distinct=3).run(df, CTX)[0]
        assert result.status is Status.FAIL

    def test_handles_empty_batch(self) -> None:
        df = pd.DataFrame({"client_version": pd.Series([], dtype="object")})
        result = CardinalityCheck("cp", "client_version", max_distinct=3).run(df, CTX)[0]
        assert result.status is Status.PASS
