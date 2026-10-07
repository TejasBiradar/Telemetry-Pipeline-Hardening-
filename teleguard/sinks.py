"""Where check results and alerts go. `MemorySink` for tests; `PostgresSink` for real runs,
writing into the schema in `db/migrations/001_schema_n_pipelines.sql` (owned jointly B/C per
ARCHITECTURE.md).

Writes are idempotent: `PostgresSink` upserts alerts on `(pipeline_id, alert_id)`, so
re-processing the same batch never duplicates an alert (BUILD_PLAN.md §3.9).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from teleguard.alerts.manager import severity_for_status
from teleguard.drift.baseline import BaselineStore
from teleguard.models import Alert, CheckResult, CheckType, Status

# CheckResult.check names are "<kind>:<field>"; this maps the kind prefix to the
# `drift_detections.drift_type` vocabulary used by db/migrations/001_schema_n_pipelines.sql.
_DRIFT_TYPE = {"psi": "psi", "ks": "ks_test", "oov_rate": "oov", "template_drift": "template_change"}


class Sink(Protocol):
    def record_results(self, results: list[CheckResult]) -> None: ...

    def record_alerts(self, alerts: list[Alert]) -> None: ...

    def record_baselines(self, checkpoint: str, baselines: BaselineStore) -> None: ...


@dataclass
class MemorySink:
    """In-process sink for tests: nothing leaves the Python process."""

    results: list[CheckResult] = field(default_factory=list)
    alerts: dict[str, Alert] = field(default_factory=dict)  # keyed by alert_id, like the DB upsert

    def record_results(self, results: list[CheckResult]) -> None:
        self.results.extend(results)

    def record_alerts(self, alerts: list[Alert]) -> None:
        for a in alerts:
            self.alerts[a.alert_id] = a

    def record_baselines(self, checkpoint: str, baselines: BaselineStore) -> None:
        pass  # nothing to assert against in tests; PostgresSink is where this matters


class PostgresSink:
    """Writes into `pipelines/<name>`'s registered row. `pipeline_id` and `run_id` are the
    caller's responsibility (pipeline/run registration is an orchestration concern, not a
    detection one) — pass the ids from `pipelines` / `pipeline_runs`."""

    def __init__(self, dsn: str, pipeline_id: int, run_id: int) -> None:
        self.dsn = dsn
        self.pipeline_id = pipeline_id
        self.run_id = run_id

    def _connect(self) -> Any:
        import psycopg  # imported lazily: tests that only use MemorySink don't need it installed
        return psycopg.connect(self.dsn)

    def record_results(self, results: list[CheckResult]) -> None:
        if not results:
            return
        with self._connect() as conn, conn.cursor() as cur:
            for r in results:
                cur.execute(
                    "INSERT INTO check_results (pipeline_id, run_id, checkpoint, check_name, "
                    "check_type, status, details, fields_affected) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (self.pipeline_id, self.run_id, r.checkpoint, r.check, r.check_type.value,
                     r.status.value, json.dumps(r.details), [r.field] if r.field else []),
                )
                self._maybe_record_drift(cur, r)
            conn.commit()

    def _maybe_record_drift(self, cur: Any, r: CheckResult) -> None:
        if r.check_type not in (CheckType.NUMERIC_DRIFT, CheckType.TEXT_DRIFT):
            return
        prefix = r.check.split(":", 1)[0]
        drift_type = _DRIFT_TYPE.get(prefix)
        if drift_type is None or r.status is Status.INSUFFICIENT_DATA:
            return
        details = r.details
        cur.execute(
            "INSERT INTO drift_detections (pipeline_id, run_id, checkpoint, field_name, "
            "segment, drift_type, severity, baseline_value, current_value, threshold, message) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (self.pipeline_id, self.run_id, r.checkpoint, r.field, r.segment or "all",
             drift_type, severity_for_status(r.status),
             details.get("baseline") or details.get("score"), details.get("current") or details.get("score"),
             details.get("threshold"), r.message),
        )

    def record_alerts(self, alerts: list[Alert]) -> None:
        if not alerts:
            return
        with self._connect() as conn, conn.cursor() as cur:
            for a in alerts:
                cur.execute(
                    "INSERT INTO alerts (pipeline_id, run_id, alert_id, severity, category, "
                    "field_name, source_segment, message) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (pipeline_id, alert_id) DO UPDATE SET "
                    "severity = EXCLUDED.severity, message = EXCLUDED.message",
                    (self.pipeline_id, self.run_id, a.alert_id, a.severity, "detection",
                     a.root_field, a.segment, a.message),
                )
            conn.commit()

    def record_baselines(self, checkpoint: str, baselines: BaselineStore) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            for (cp, field_name, segment), b in baselines.numeric.items():
                if cp != checkpoint:
                    continue
                arr = np.asarray(b.sample, dtype=float)
                percentiles = np.percentile(arr, [0, 25, 50, 75, 95, 100]) if len(arr) else [None] * 6
                cur.execute(
                    "INSERT INTO baseline_profiles (pipeline_id, checkpoint, field_name, "
                    "segment, p0, p25, p50, p75, p95, p100, mean, stddev, sample_count) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (pipeline_id, checkpoint, field_name, COALESCE(segment, 'all')) "
                    "DO UPDATE SET p0=EXCLUDED.p0, p25=EXCLUDED.p25, p50=EXCLUDED.p50, "
                    "p75=EXCLUDED.p75, p95=EXCLUDED.p95, p100=EXCLUDED.p100, mean=EXCLUDED.mean, "
                    "stddev=EXCLUDED.stddev, sample_count=EXCLUDED.sample_count",
                    (self.pipeline_id, cp, field_name, segment, *percentiles, b.mean, b.std,
                     b.sample_count),
                )
            for (cp, field_name, segment), t in baselines.text.items():
                if cp != checkpoint:
                    continue
                cur.execute(
                    "INSERT INTO baseline_profiles (pipeline_id, checkpoint, field_name, "
                    "segment, cardinality, top_values, sample_count) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (pipeline_id, checkpoint, field_name, COALESCE(segment, 'all')) "
                    "DO UPDATE SET cardinality=EXCLUDED.cardinality, top_values=EXCLUDED.top_values, "
                    "sample_count=EXCLUDED.sample_count",
                    (self.pipeline_id, cp, field_name, segment, len(t.vocabulary),
                     json.dumps(dict(sorted(t.template_counts.items(), key=lambda kv: -kv[1])[:20])),
                     t.sample_count),
                )
            conn.commit()
