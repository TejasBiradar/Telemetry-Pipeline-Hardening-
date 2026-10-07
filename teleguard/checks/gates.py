"""Rule-based gates: schema, null-rate, range, volume, key-set and cardinality.

Deterministic, threshold-based, no statistics beyond counting (CLAUDE.md rule 5: checks
never decide from an LLM, pass/fail is deterministic). Statistical drift detectors live in
`teleguard.drift` instead.

Each check is bound to its checkpoint at construction time (the contract factory always
knows it), so `run(df, ctx)` only needs the batch context, matching the shared `Check`
interface.
"""

from __future__ import annotations

import pandas as pd

from teleguard.checks.base import MIN_SAMPLE_SIZE, segments
from teleguard.models import BatchContext, CheckResult, CheckType, Status

_NUMERIC_DTYPES = ("int", "float")


class SchemaCheck:
    """Field must exist and (if given) have a dtype compatible with `dtype`."""

    check_type = CheckType.SCHEMA

    def __init__(self, checkpoint: str, field: str, dtype: str | None = None) -> None:
        self.checkpoint = checkpoint
        self.field = field
        self.dtype = dtype
        self.name = f"schema:{field}"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        if self.field not in df.columns:
            return [CheckResult(check=self.name, check_type=CheckType.SCHEMA,
                               checkpoint=self.checkpoint, status=Status.FAIL, field=self.field,
                               message=f"'{self.field}' is missing from this batch")]
        if self.dtype is None:
            return [CheckResult(check=self.name, check_type=CheckType.SCHEMA,
                               checkpoint=self.checkpoint, status=Status.PASS, field=self.field)]
        actual = str(df[self.field].dtype)
        ok = (any(actual.startswith(p) for p in _NUMERIC_DTYPES) if self.dtype == "numeric"
              else actual.startswith(self.dtype))
        status = Status.PASS if ok else Status.FAIL
        message = "" if ok else f"'{self.field}' is {actual}, expected {self.dtype}"
        return [CheckResult(check=self.name, check_type=CheckType.SCHEMA,
                           checkpoint=self.checkpoint, status=status, field=self.field,
                           message=message, details={"expected": self.dtype, "actual": actual})]


class NullRateCheck:
    check_type = CheckType.NULLS

    def __init__(self, checkpoint: str, field: str, max_null_rate: float) -> None:
        self.checkpoint = checkpoint
        self.field = field
        self.max_null_rate = max_null_rate
        self.name = f"null_rate:{field}"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        if self.field not in df.columns:
            return [CheckResult(check=self.name, check_type=CheckType.NULLS,
                               checkpoint=self.checkpoint, status=Status.ERROR, field=self.field,
                               message=f"'{self.field}' is missing from this batch")]
        results = []
        for segment, part in segments(df, ctx):
            if len(part) < MIN_SAMPLE_SIZE:
                results.append(CheckResult(
                    check=self.name, check_type=CheckType.NULLS, checkpoint=self.checkpoint,
                    status=Status.INSUFFICIENT_DATA, field=self.field, segment=segment,
                    message=f"only {len(part)} rows, below the minimum of {MIN_SAMPLE_SIZE}"))
                continue
            rate = float(part[self.field].isna().mean())
            status = Status.PASS if rate <= self.max_null_rate else Status.FAIL
            results.append(CheckResult(
                check=self.name, check_type=CheckType.NULLS, checkpoint=self.checkpoint,
                status=status, field=self.field, segment=segment,
                message="" if status is Status.PASS else
                f"null rate {rate:.1%} exceeds the {self.max_null_rate:.1%} limit",
                details={"null_rate": rate, "threshold": self.max_null_rate, "rows": len(part)}))
        return results


class RangeCheck:
    check_type = CheckType.RANGE

    def __init__(self, checkpoint: str, field: str, min: float | None = None,
                max: float | None = None, max_violation_rate: float = 0.0) -> None:
        self.checkpoint = checkpoint
        self.field = field
        self.min = min
        self.max = max
        self.max_violation_rate = max_violation_rate
        self.name = f"range:{field}"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        if self.field not in df.columns:
            return [CheckResult(check=self.name, check_type=CheckType.RANGE,
                               checkpoint=self.checkpoint, status=Status.ERROR, field=self.field,
                               message=f"'{self.field}' is missing from this batch")]
        results = []
        for segment, part in segments(df, ctx):
            values = part[self.field].dropna()
            if len(values) < MIN_SAMPLE_SIZE:
                results.append(CheckResult(
                    check=self.name, check_type=CheckType.RANGE, checkpoint=self.checkpoint,
                    status=Status.INSUFFICIENT_DATA, field=self.field, segment=segment,
                    message=f"only {len(values)} non-null rows, below the minimum of "
                    f"{MIN_SAMPLE_SIZE}"))
                continue
            below = (values < self.min) if self.min is not None else pd.Series(False, index=values.index)
            above = (values > self.max) if self.max is not None else pd.Series(False, index=values.index)
            rate = float((below | above).mean())
            status = Status.PASS if rate <= self.max_violation_rate else Status.FAIL
            results.append(CheckResult(
                check=self.name, check_type=CheckType.RANGE, checkpoint=self.checkpoint,
                status=status, field=self.field, segment=segment,
                message="" if status is Status.PASS else
                f"{rate:.1%} of values fall outside [{self.min}, {self.max}]",
                details={"violation_rate": rate, "min": self.min, "max": self.max}))
        return results


class VolumeCheck:
    """Whole-batch row count against an expected band. Catches a feed going silent or
    duplicating; a tighter, per-segment version is the natural next step."""

    check_type = CheckType.VOLUME

    def __init__(self, checkpoint: str, min_rows: int | None, max_rows: int | None) -> None:
        self.checkpoint = checkpoint
        self.min_rows = min_rows
        self.max_rows = max_rows
        self.name = "volume"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        n = len(df)
        too_few = self.min_rows is not None and n < self.min_rows
        too_many = self.max_rows is not None and n > self.max_rows
        status = Status.FAIL if (too_few or too_many) else Status.PASS
        message = ("" if status is Status.PASS else
                  f"{n} rows, expected between {self.min_rows} and {self.max_rows}")
        return [CheckResult(check=self.name, check_type=CheckType.VOLUME,
                           checkpoint=self.checkpoint, status=status, message=message,
                           details={"rows": n, "min_rows": self.min_rows, "max_rows": self.max_rows})]


class KeySetCheck:
    """A categorical field must only take allowed values. Uses CheckType.SCHEMA: a new
    'key_set' CheckType would be a shared-contract change (CLAUDE.md rule 7)."""

    check_type = CheckType.SCHEMA

    def __init__(self, checkpoint: str, field: str, allowed: list[str]) -> None:
        self.checkpoint = checkpoint
        self.field = field
        self.allowed = set(allowed)
        self.name = f"key_set:{field}"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        if self.field not in df.columns:
            return [CheckResult(check=self.name, check_type=CheckType.SCHEMA,
                               checkpoint=self.checkpoint, status=Status.ERROR, field=self.field,
                               message=f"'{self.field}' is missing from this batch")]
        values = set(df[self.field].dropna().astype(str).unique())
        unexpected = sorted(values - self.allowed)
        status = Status.PASS if not unexpected else Status.WARN
        message = "" if not unexpected else f"unexpected values: {', '.join(unexpected[:5])}"
        return [CheckResult(check=self.name, check_type=CheckType.SCHEMA,
                           checkpoint=self.checkpoint, status=status, field=self.field,
                           message=message, details={"unexpected": unexpected})]


class CardinalityCheck:
    """A field's distinct-value count must stay within a band. Uses CheckType.SCHEMA (see
    KeySetCheck's note)."""

    check_type = CheckType.SCHEMA

    def __init__(self, checkpoint: str, field: str, max_distinct: int) -> None:
        self.checkpoint = checkpoint
        self.field = field
        self.max_distinct = max_distinct
        self.name = f"cardinality:{field}"

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        if self.field not in df.columns:
            return [CheckResult(check=self.name, check_type=CheckType.SCHEMA,
                               checkpoint=self.checkpoint, status=Status.ERROR, field=self.field,
                               message=f"'{self.field}' is missing from this batch")]
        distinct = int(df[self.field].nunique(dropna=True))
        status = Status.PASS if distinct <= self.max_distinct else Status.FAIL
        message = "" if status is Status.PASS else (
            f"{distinct} distinct values, expected at most {self.max_distinct}")
        return [CheckResult(check=self.name, check_type=CheckType.SCHEMA,
                           checkpoint=self.checkpoint, status=status, field=self.field,
                           message=message, details={"distinct": distinct})]
