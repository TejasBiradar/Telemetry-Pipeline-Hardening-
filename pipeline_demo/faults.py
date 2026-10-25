"""Demo faults for the pipeline trigger. Detection does not live here.

These match the user-behavior catalogue: one run is one batch, so the fault
applies to that whole run for the client version it names.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class DemoFault:
    fault_id: str
    label: str
    detail: str


FAULTS: tuple[DemoFault, ...] = (
    DemoFault("clean", "Clean data", "No fault. Negative control."),
    DemoFault(
        "unit_change_android",
        "Unit change (Android 5.2.0)",
        "duration_ms is already in seconds, so the pipeline's conversion collapses it.",
    ),
    DemoFault(
        "new_nullable_web",
        "New nullable (web 1.5.2)",
        "Some user ids arrive null. The job still finishes; filter_sessions drops those rows.",
    ),
    DemoFault(
        "type_change_android",
        "Type change (Android 5.1.3)",
        "duration_ms arrives as text. The job fails when it tries to treat that as a number.",
    ),
    DemoFault(
        "action_flood_ios",
        "Volume drop (iOS 6.1.0)",
        "Most iOS 6.1.0 events are missing. The job still finishes with a thinner batch.",
    ),
    DemoFault(
        "feed_stops_ios",
        "Feed stops (iOS 6.0.1)",
        "iOS 6.0.1 sends nothing. Other versions still run.",
    ),
)

VERSIONS: tuple[str, ...] = ("1.2.0", "5.2.0", "1.5.2", "5.1.3", "6.1.0", "6.0.1")


def list_faults() -> list[DemoFault]:
    return list(FAULTS)


def fault_by_id(fault_id: str) -> DemoFault:
    for fault in FAULTS:
        if fault.fault_id == fault_id:
            return fault
    known = ", ".join(fault.fault_id for fault in FAULTS)
    raise ValueError(f"unknown fault {fault_id!r}; expected one of: {known}")


def apply_fault(
    events: list[dict[str, object]],
    fault_id: str,
    *,
    seed: int = 123,
) -> list[dict[str, object]]:
    """Return a copy of ``events`` with ``fault_id`` applied. ``clean`` is a copy only."""
    fault_by_id(fault_id)
    out = copy.deepcopy(events)
    if fault_id == "clean":
        return out
    if fault_id == "unit_change_android":
        _scale_duration(out, "5.2.0", 1000.0)
        return out
    if fault_id == "new_nullable_web":
        _null_user_ids(out, "1.5.2", random.Random(seed), 0.3)
        return out
    if fault_id == "type_change_android":
        _stringify_duration(out, "5.1.3")
        return out
    if fault_id == "action_flood_ios":
        return _drop_version(out, "6.1.0", random.Random(seed), 0.7)
    if fault_id == "feed_stops_ios":
        return [event for event in out if event.get("client_version") != "6.0.1"]
    raise ValueError(f"unhandled fault {fault_id!r}")


def _payload(event: dict[str, object]) -> dict[str, object]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise TypeError("event payload must be an object")
    return payload


def _scale_duration(events: list[dict[str, object]], version: str, factor: float) -> None:
    for event in events:
        if event.get("client_version") != version:
            continue
        payload = _payload(event)
        value = payload.get("duration_ms")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("duration_ms must be numeric before a unit change")
        payload["duration_ms"] = float(value) / factor


def _null_user_ids(
    events: list[dict[str, object]],
    version: str,
    rng: random.Random,
    null_rate: float,
) -> None:
    for event in events:
        if event.get("client_version") == version and rng.random() < null_rate:
            event["user_id"] = None


def _stringify_duration(events: list[dict[str, object]], version: str) -> None:
    for event in events:
        if event.get("client_version") != version:
            continue
        payload = _payload(event)
        payload["duration_ms"] = f"{payload.get('duration_ms')}ms"


def _drop_version(
    events: list[dict[str, object]],
    version: str,
    rng: random.Random,
    drop_rate: float,
) -> list[dict[str, object]]:
    kept: list[dict[str, object]] = []
    for event in events:
        if event.get("client_version") == version and rng.random() < drop_rate:
            continue
        kept.append(event)
    return kept
