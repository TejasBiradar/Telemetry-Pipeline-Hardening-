"""Guard runtime: off/observe/enforce behaviour exactly as ARCHITECTURE.md §3.1 specifies,
plus fail-open on a crashing check (CLAUDE.md: checks never take the pipeline down)."""

from __future__ import annotations

import pandas as pd
import pytest

from teleguard.alerts.manager import AlertManager
from teleguard.guard import BatchRejectedError, Guard
from teleguard.models import BatchContext, CheckResult, CheckType, GuardMode, Status
from teleguard.sinks import MemorySink

CTX = BatchContext(pipeline="p", batch_id="b1")


class _AlwaysPass:
    name = "always_pass"
    check_type = CheckType.SCHEMA

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        return [CheckResult(check=self.name, check_type=self.check_type, checkpoint="cp",
                            status=Status.PASS)]


class _AlwaysFail:
    name = "always_fail"
    check_type = CheckType.RANGE

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        return [CheckResult(check=self.name, check_type=self.check_type, checkpoint="cp",
                            status=Status.FAIL, field="x", message="boom")]


class _AlwaysCrashes:
    name = "always_crashes"
    check_type = CheckType.SCHEMA

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        raise RuntimeError("this check is broken")


def _guard(checks: list, mode: GuardMode, sink: MemorySink) -> Guard:
    return Guard(mode=mode, checks_for=lambda cp: checks, sink=sink, alerts=AlertManager())


def test_off_mode_runs_no_checks_and_returns_the_same_object() -> None:
    sink = MemorySink()
    df = pd.DataFrame({"x": [1]})
    guard = _guard([_AlwaysFail()], GuardMode.OFF, sink)

    result = guard.check("cp", df, CTX)

    assert result is df
    assert sink.results == []


def test_observe_mode_records_results_but_never_raises() -> None:
    sink = MemorySink()
    df = pd.DataFrame({"x": [1]})
    guard = _guard([_AlwaysFail()], GuardMode.OBSERVE, sink)

    result = guard.check("cp", df, CTX)

    assert result is df  # untouched, even with a FAIL result recorded
    assert len(sink.results) == 1
    assert sink.results[0].status is Status.FAIL
    assert len(sink.alerts) == 1  # the alert manager still ran


def test_observe_mode_passes_through_with_a_passing_check() -> None:
    sink = MemorySink()
    df = pd.DataFrame({"x": [1]})
    guard = _guard([_AlwaysPass()], GuardMode.OBSERVE, sink)

    guard.check("cp", df, CTX)

    assert sink.results[0].status is Status.PASS
    assert sink.alerts == {}


def test_enforce_mode_raises_on_a_failing_check() -> None:
    sink = MemorySink()
    df = pd.DataFrame({"x": [1]})
    guard = _guard([_AlwaysFail()], GuardMode.ENFORCE, sink)

    with pytest.raises(BatchRejectedError):
        guard.check("cp", df, CTX)

    assert len(sink.results) == 1  # still recorded, even though the batch was rejected


def test_enforce_mode_passes_through_when_nothing_fails() -> None:
    sink = MemorySink()
    df = pd.DataFrame({"x": [1]})
    guard = _guard([_AlwaysPass()], GuardMode.ENFORCE, sink)

    result = guard.check("cp", df, CTX)

    assert result is df


def test_a_crashing_check_is_recorded_as_error_and_never_raised() -> None:
    sink = MemorySink()
    df = pd.DataFrame({"x": [1]})
    guard = _guard([_AlwaysCrashes()], GuardMode.ENFORCE, sink)

    result = guard.check("cp", df, CTX)  # must not raise: fail-open

    assert result is df
    assert sink.results[0].status is Status.ERROR
    assert "this check is broken" in sink.results[0].message


def test_mutating_a_check_does_not_mutate_the_original_dataframe() -> None:
    class _Mutates:
        name = "mutates"
        check_type = CheckType.SCHEMA

        def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
            df["x"] = 999  # a buggy check that violates the "never modifies df" rule
            return [CheckResult(check=self.name, check_type=self.check_type, checkpoint="cp",
                                status=Status.PASS)]

    sink = MemorySink()
    df = pd.DataFrame({"x": [1]})
    guard = _guard([_Mutates()], GuardMode.OBSERVE, sink)

    guard.check("cp", df, CTX)

    assert df["x"].tolist() == [1]  # guard.py's own copy absorbed the mutation, not the original
