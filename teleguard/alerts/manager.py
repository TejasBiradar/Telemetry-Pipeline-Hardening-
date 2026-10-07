"""Alert manager: groups raw check failures into one alert per problem, deduplicated and
scored by severity, optionally traced to affected outputs via A's lineage graph.

Stateful across calls: a problem that is still failing on the next batch updates the same
alert rather than creating a new one; a problem that stops failing is considered resolved
and its alert is dropped from `open_alerts` (BUILD_PLAN.md §3.6 "alert storm").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from teleguard.models import Alert, BatchContext, CheckResult, LineageStep, Status

_PROBLEM_STATUSES = (Status.FAIL, Status.WARN, Status.ERROR)
_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}
_SEVERITY_FOR_STATUS = {Status.FAIL: "high", Status.WARN: "medium", Status.ERROR: "medium"}


def severity_for_status(status: Status) -> str:
    return _SEVERITY_FOR_STATUS.get(status, "low")


class LineageLookup(Protocol):
    """A's code-graph lineage, consumed here once `teleguard/lineage/` exists. Until then,
    pass `None` (the default) — alerts are still produced, just without a lineage trace."""

    def trace(self, field: str) -> list[LineageStep]: ...

    def affected_outputs(self, field: str) -> list[str]: ...


def _alert_id(pipeline: str, root_field: str, segment: str | None) -> str:
    return f"{pipeline}:{root_field}:{segment or 'all'}"


def _message(r: CheckResult) -> str:
    if r.message:
        where = f" ({r.segment})" if r.segment else ""
        return f"{r.check}{where}: {r.message}"
    return f"{r.check} returned {r.status.value}"


Key = tuple[str, str, str | None]  # (checkpoint, root_field, segment)


@dataclass
class AlertManager:
    """`guard.check()` is called once per checkpoint, so one `process()` call only ever sees
    that checkpoint's results. Keying on checkpoint too (not just field/segment) matters:
    without it, evaluating `after_clean` would wrongly "resolve" an alert that actually
    belongs to `after_aggregate`, just because this call never mentioned it."""

    open_alerts: dict[Key, Alert] = field(default_factory=dict)

    def process(self, results: list[CheckResult], ctx: BatchContext,
               lineage: LineageLookup | None = None) -> list[Alert]:
        """Returns the alerts that are new or changed this call (what the sink should persist).
        Resolved alerts (no longer failing) are dropped from `open_alerts` but not returned."""
        problems = [r for r in results if r.status in _PROBLEM_STATUSES]
        checkpoints_seen = {r.checkpoint for r in results}
        still_bad: set[Key] = set()
        changed: list[Alert] = []

        for r in problems:
            root_field = r.field or r.check
            key: Key = (r.checkpoint, root_field, r.segment)
            still_bad.add(key)
            severity = severity_for_status(r.status)
            existing = self.open_alerts.get(key)
            if existing is None:
                alert = Alert(
                    alert_id=_alert_id(ctx.pipeline, root_field, r.segment),
                    pipeline=ctx.pipeline, batch_id=ctx.batch_id, severity=severity,
                    message=_message(r), root_field=r.field, segment=r.segment,
                )
                if lineage is not None and r.field:
                    alert.lineage = lineage.trace(r.field)
                    alert.affected_outputs = lineage.affected_outputs(r.field)
                self.open_alerts[key] = alert
                changed.append(alert)
            else:
                worse = _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(existing.severity, 0)
                if worse or existing.message != _message(r):
                    existing.severity = severity if worse else existing.severity
                    existing.message = _message(r)
                    changed.append(existing)

        for key in [k for k in self.open_alerts
                   if k[0] in checkpoints_seen and k not in still_bad]:
            del self.open_alerts[key]

        return changed
