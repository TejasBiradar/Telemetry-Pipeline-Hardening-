"""Fault catalogue: deliberately breaks generated telemetry in known ways, and records the
ground truth of what was broken, where, and from which batch — so detection can be scored
honestly against something, not just eyeballed.

Operates on the raw event batches `datagen.generate.generate()` produces (before they're
written to files and read by the pipeline), since that's where a real-world fault like "a
field changes unit" actually originates — upstream of the frozen pipeline, never inside it.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Iterator
from dataclasses import dataclass
from dataclasses import field as dc_field
from enum import Enum
from typing import Any

Event = dict[str, Any]
Batch = list[Event]

NEW_ERROR_TEMPLATES = (
    "upstream dependency unavailable",
    "rate limit exceeded, retry later",
    "database connection pool exhausted",
)


class FaultType(str, Enum):
    UNIT_CHANGE = "unit_change"
    FEED_STOPS = "feed_stops"
    NEW_NULLABLE = "new_nullable"
    TYPE_CHANGE = "type_change"
    GRADUAL_DRIFT = "gradual_drift"
    TEXT_CHANGE = "text_change"
    VOLUME_DROP = "volume_drop"
    CLEAN = "clean"


@dataclass(frozen=True)
class Injection:
    """Ground truth: what was broken, where, and from when. `onset_batch` is 1-indexed;
    that batch and every one after it carries the fault."""

    injection_id: str
    fault_type: FaultType
    field_name: str | None
    segment: str | None
    onset_batch: int
    details: dict[str, Any] = dc_field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"injection_id": self.injection_id, "fault_type": self.fault_type.value,
                "field_name": self.field_name, "segment": self.segment,
                "onset_batch": self.onset_batch, "details": self.details}


def _copy_batches(batches: list[Batch]) -> list[Batch]:
    return copy.deepcopy(batches)


def _affected(batches: list[Batch], onset_batch: int, segment: str) -> Iterator[tuple[int, Event]]:
    """Yield (1-indexed batch number, event) for every event in `segment` from `onset_batch` on."""
    for i, batch in enumerate(batches, start=1):
        if i < onset_batch:
            continue
        for event in batch:
            if event.get("client_version") == segment:
                yield i, event


def inject_unit_change(batches: list[Batch], onset_batch: int, segment: str,
                       field_name: str = "duration_ms", factor: float = 1000.0,
                       ) -> tuple[list[Batch], Injection]:
    """From `onset_batch` on, `segment` sends `field_name` already divided by `factor` —
    e.g. seconds under a field still named `duration_ms` — so the pipeline's own ms->s
    conversion double-applies. This is the brief's "a field changes unit" scenario."""
    out = _copy_batches(batches)
    for _, event in _affected(out, onset_batch, segment):
        event["payload"][field_name] = event["payload"][field_name] / factor
    return out, Injection(f"unit_change:{segment}:{onset_batch}", FaultType.UNIT_CHANGE,
                          field_name, segment, onset_batch, {"factor": factor})


def inject_feed_stops(batches: list[Batch], onset_batch: int, segment: str,
                      ) -> tuple[list[Batch], Injection]:
    """From `onset_batch` on, `segment` emits nothing at all — "a client version stops
    emitting", word for word."""
    out = _copy_batches(batches)
    for i, batch in enumerate(out, start=1):
        if i >= onset_batch:
            batch[:] = [e for e in batch if e.get("client_version") != segment]
    return out, Injection(f"feed_stops:{segment}:{onset_batch}", FaultType.FEED_STOPS,
                          None, segment, onset_batch, {})


def inject_new_nullable(batches: list[Batch], onset_batch: int, segment: str, rng: random.Random,
                        field_name: str = "user_id", null_rate: float = 0.3,
                        ) -> tuple[list[Batch], Injection]:
    """From `onset_batch` on, `segment` starts sending `field_name` null at `null_rate` —
    "a schema gains a nullable that downstream assumed present"."""
    out = _copy_batches(batches)
    for _, event in _affected(out, onset_batch, segment):
        if rng.random() < null_rate:
            event[field_name] = None
    return out, Injection(f"new_nullable:{segment}:{onset_batch}", FaultType.NEW_NULLABLE,
                          field_name, segment, onset_batch, {"null_rate": null_rate})


def inject_type_change(batches: list[Batch], onset_batch: int, segment: str,
                       field_name: str = "duration_ms") -> tuple[list[Batch], Injection]:
    """From `onset_batch` on, `field_name` arrives as text (e.g. "1483ms") instead of a
    number."""
    out = _copy_batches(batches)
    for _, event in _affected(out, onset_batch, segment):
        event["payload"][field_name] = f"{event['payload'][field_name]}ms"
    return out, Injection(f"type_change:{segment}:{onset_batch}", FaultType.TYPE_CHANGE,
                          field_name, segment, onset_batch, {})


def inject_gradual_drift(batches: list[Batch], onset_batch: int, segment: str,
                         field_name: str = "duration_ms", pct_per_batch: float = 0.08,
                         ) -> tuple[list[Batch], Injection]:
    """From `onset_batch` on, `field_name` creeps up by `pct_per_batch` every batch — a slow
    drift rather than a sudden shift, which a single-batch-vs-baseline check may take longer
    to notice (that lag, measured honestly, is itself a finding)."""
    out = _copy_batches(batches)
    for i, event in _affected(out, onset_batch, segment):
        steps = i - onset_batch + 1
        event["payload"][field_name] *= (1 + pct_per_batch) ** steps
    return out, Injection(f"gradual_drift:{segment}:{onset_batch}", FaultType.GRADUAL_DRIFT,
                          field_name, segment, onset_batch, {"pct_per_batch": pct_per_batch})


def inject_text_change(batches: list[Batch], onset_batch: int, segment: str, rng: random.Random,
                       field_name: str = "error_message", rate: float = 0.6,
                       ) -> tuple[list[Batch], Injection]:
    """From `onset_batch` on, a share of `segment`'s error messages switch to templates never
    seen in the baseline vocabulary."""
    out = _copy_batches(batches)
    for _, event in _affected(out, onset_batch, segment):
        if event["payload"].get(field_name) is not None and rng.random() < rate:
            event["payload"][field_name] = rng.choice(NEW_ERROR_TEMPLATES)
    return out, Injection(f"text_change:{segment}:{onset_batch}", FaultType.TEXT_CHANGE,
                          field_name, segment, onset_batch, {"rate": rate})


def inject_volume_drop(batches: list[Batch], onset_batch: int, segment: str, rng: random.Random,
                       drop_rate: float = 0.6) -> tuple[list[Batch], Injection]:
    """From `onset_batch` on, `segment` still sends data, just `drop_rate` less of it — the
    partial counterpart to `inject_feed_stops`'s total silence."""
    out = _copy_batches(batches)
    for i, batch in enumerate(out, start=1):
        if i >= onset_batch:
            batch[:] = [e for e in batch
                       if e.get("client_version") != segment or rng.random() >= drop_rate]
    return out, Injection(f"volume_drop:{segment}:{onset_batch}", FaultType.VOLUME_DROP,
                          None, segment, onset_batch, {"drop_rate": drop_rate})


def inject_clean(batches: list[Batch]) -> tuple[list[Batch], Injection]:
    """No fault at all — the negative control used to measure false alarms honestly."""
    out = _copy_batches(batches)
    return out, Injection("clean", FaultType.CLEAN, None, None, len(out) + 1, {})
