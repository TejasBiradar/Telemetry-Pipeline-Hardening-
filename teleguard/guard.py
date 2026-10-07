"""Guard runtime: the one function the pipeline calls at each checkpoint.

    df = guard.check(checkpoint, df, ctx)

Behaviour per mode (ARCHITECTURE.md §3.1), implemented exactly as documented there:
- off:     returns the same object untouched. No checks run.
- observe: runs checks on a copy, records results, returns the original untouched. A check
           that raises is recorded as an ERROR result, never re-raised (fail-open).
- enforce: same as observe, then applies the fail policy if any check returned FAIL. The
           default policy raises `BatchRejectedError`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from teleguard.alerts.manager import AlertManager, LineageLookup
from teleguard.checks.base import Check
from teleguard.models import BatchContext, CheckResult, CheckType, GuardMode, Status
from teleguard.sinks import Sink


class BatchRejectedError(Exception):
    def __init__(self, checkpoint: str, failures: list[CheckResult]) -> None:
        self.checkpoint = checkpoint
        self.failures = failures
        names = ", ".join(f"{f.check}" + (f"[{f.segment}]" if f.segment else "") for f in failures)
        super().__init__(f"batch rejected at '{checkpoint}': {names}")


FailPolicy = Callable[[str, list[CheckResult]], None]


def block_on_any_failure(checkpoint: str, failures: list[CheckResult]) -> None:
    raise BatchRejectedError(checkpoint, failures)


@dataclass
class Guard:
    mode: GuardMode
    checks_for: Callable[[str], list[Check]]
    sink: Sink
    alerts: AlertManager = field(default_factory=AlertManager)
    lineage: LineageLookup | None = None
    fail_policy: FailPolicy = block_on_any_failure

    def check(self, checkpoint: str, df: pd.DataFrame, ctx: BatchContext) -> pd.DataFrame:
        if self.mode is GuardMode.OFF:
            return df

        results = self._run_all(checkpoint, df.copy(deep=True), ctx)
        self.sink.record_results(results)
        changed_alerts = self.alerts.process(results, ctx, self.lineage)
        self.sink.record_alerts(changed_alerts)

        if self.mode is GuardMode.ENFORCE:
            failures = [r for r in results if r.status is Status.FAIL]
            if failures:
                self.fail_policy(checkpoint, failures)

        return df

    def _run_all(self, checkpoint: str, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]:
        results: list[CheckResult] = []
        for chk in self.checks_for(checkpoint):
            try:
                results.extend(chk.run(df, ctx))
            except Exception as exc:  # noqa: BLE001 - a crashing check is fail-open, not fatal
                results.append(CheckResult(
                    check=getattr(chk, "name", type(chk).__name__),
                    check_type=getattr(chk, "check_type", CheckType.SCHEMA),
                    checkpoint=checkpoint, status=Status.ERROR,
                    message=f"check crashed: {type(exc).__name__}: {exc}",
                ))
        return results
