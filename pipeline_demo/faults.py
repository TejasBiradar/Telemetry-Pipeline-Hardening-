"""Demo faults for the pipeline trigger. Detection does not live here.

Each pipeline has its own catalogue. One run is one batch, so the chosen fault
applies to that whole run.
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


USER_BEHAVIOR_FAULTS: tuple[DemoFault, ...] = (
    DemoFault("clean", "Clean sessions", "No fault. Negative control for session engagement."),
    DemoFault(
        "unit_change_android",
        "Session duration unit slip (Android 5.2.0)",
        "duration_ms is already in seconds, so filter_sessions' /1000 collapses session length.",
    ),
    DemoFault(
        "new_nullable_web",
        "Null session user_id (web 1.5.2)",
        "Some user ids arrive null. The job still finishes; filter_sessions drops those rows.",
    ),
    DemoFault(
        "type_change_android",
        "Session duration as text (Android 5.1.3)",
        "duration_ms arrives as text. The job fails when filter_sessions treats it as a number.",
    ),
    DemoFault(
        "action_flood_ios",
        "Fewer iOS sessions (6.1.0)",
        "Most iOS 6.1.0 events are missing. Aggregate still finishes on a thinner session set.",
    ),
    DemoFault(
        "feed_stops_ios",
        "iOS session feed stops (6.0.1)",
        "iOS 6.0.1 sends nothing. Other client versions still produce sessions.",
    ),
)

PAYMENT_FAULTS: tuple[DemoFault, ...] = (
    DemoFault("clean", "Clean data", "No fault. Negative control."),
    DemoFault(
        "new_nullable_user",
        "New nullable user_id",
        "Some user ids arrive null. The job still finishes; clean drops those rows.",
    ),
    DemoFault(
        "amount_already_usd",
        "Unit change (amount)",
        "amount_cents is already in dollars, so /100 collapses the value.",
    ),
    DemoFault(
        "type_change_amount",
        "Type change (amount_cents)",
        "amount_cents arrives as text. The job fails on numeric compare or convert.",
    ),
    DemoFault(
        "bad_status",
        "Unknown status values",
        "Some rows use status values outside the allowed set; clean drops them.",
    ),
    DemoFault(
        "volume_drop_us",
        "Volume drop (MER_US)",
        "Most North America merchant payments are missing. The job still finishes thinner.",
    ),
)

WEB_ANALYTICS_FAULTS: tuple[DemoFault, ...] = (
    DemoFault("clean", "Baseline page-view batch", "No fault. Control run for the web analytics funnel."),
    DemoFault(
        "duration_already_seconds",
        "Page duration already in seconds",
        "Android 5.2.0 sends duration_ms pre-scaled; clean's /1000 collapses page times.",
    ),
    DemoFault(
        "anonymous_web_hits",
        "Anonymous page hits (null user_id)",
        "Web 1.5.2 omits user_id on some hits. Job finishes; clean drops them before enrich.",
    ),
    DemoFault(
        "duration_sent_as_text",
        "Page duration arrives as text",
        "Android 5.1.3 sends duration_ms like '1200ms'. clean fails on numeric convert.",
    ),
    DemoFault(
        "thin_ios_page_views",
        "Thin iOS page-view traffic",
        "Most iOS 6.1.0 hits are missing. Daily metrics still roll up on a thinner funnel.",
    ),
    DemoFault(
        "ios_channel_offline",
        "iOS channel goes offline",
        "iOS 6.0.1 sends nothing this batch. Other platforms still appear in daily metrics.",
    ),
)

# Web analytics menu ids map onto the shared telemetry injectors.
_WEB_FAULT_ALIASES: dict[str, str] = {
    "duration_already_seconds": "unit_change_android",
    "anonymous_web_hits": "new_nullable_web",
    "duration_sent_as_text": "type_change_android",
    "thin_ios_page_views": "action_flood_ios",
    "ios_channel_offline": "feed_stops_ios",
}

_FAULTS_BY_PIPELINE: dict[str, tuple[DemoFault, ...]] = {
    "user_behavior": USER_BEHAVIOR_FAULTS,
    "payment_processing": PAYMENT_FAULTS,
    "web_analytics": WEB_ANALYTICS_FAULTS,
}

VERSIONS: tuple[str, ...] = ("1.2.0", "5.2.0", "1.5.2", "5.1.3", "6.1.0", "6.0.1")

# Kept for older imports / tests that call list_faults() without a pipeline.
FAULTS: tuple[DemoFault, ...] = USER_BEHAVIOR_FAULTS


def list_faults(pipeline_id: str = "user_behavior") -> list[DemoFault]:
    if pipeline_id not in _FAULTS_BY_PIPELINE:
        known = ", ".join(_FAULTS_BY_PIPELINE)
        raise ValueError(f"unknown pipeline {pipeline_id!r}; expected one of: {known}")
    return list(_FAULTS_BY_PIPELINE[pipeline_id])


def fault_by_id(fault_id: str, pipeline_id: str = "user_behavior") -> DemoFault:
    for fault in list_faults(pipeline_id):
        if fault.fault_id == fault_id:
            return fault
    known = ", ".join(fault.fault_id for fault in list_faults(pipeline_id))
    raise ValueError(
        f"unknown fault {fault_id!r} for pipeline {pipeline_id!r}; expected one of: {known}"
    )


def apply_fault(
    events: list[dict[str, object]],
    fault_id: str,
    *,
    pipeline_id: str = "user_behavior",
    seed: int = 123,
) -> list[dict[str, object]]:
    """Return a copy of ``events`` with ``fault_id`` applied for ``pipeline_id``."""
    fault_by_id(fault_id, pipeline_id)
    if pipeline_id == "payment_processing":
        return _apply_payment(events, fault_id, seed=seed)
    resolved = _WEB_FAULT_ALIASES.get(fault_id, fault_id) if pipeline_id == "web_analytics" else fault_id
    return _apply_telemetry(events, resolved, seed=seed)


def _apply_telemetry(
    events: list[dict[str, object]],
    fault_id: str,
    *,
    seed: int,
) -> list[dict[str, object]]:
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
    raise ValueError(f"unhandled telemetry fault {fault_id!r}")


def _apply_payment(
    events: list[dict[str, object]],
    fault_id: str,
    *,
    seed: int,
) -> list[dict[str, object]]:
    out = copy.deepcopy(events)
    if fault_id == "clean":
        return out
    if fault_id == "new_nullable_user":
        rng = random.Random(seed)
        for event in out:
            if rng.random() < 0.3:
                event["user_id"] = None
        return out
    if fault_id == "amount_already_usd":
        for event in out:
            value = event.get("amount_cents")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("amount_cents must be numeric before a unit change")
            event["amount_cents"] = float(value) / 100.0
        return out
    if fault_id == "type_change_amount":
        for event in out:
            event["amount_cents"] = f"{event.get('amount_cents')}c"
        return out
    if fault_id == "bad_status":
        for i, event in enumerate(out):
            if i % 5 == 0:
                event["status"] = "authorized"
        return out
    if fault_id == "volume_drop_us":
        rng = random.Random(seed)
        kept: list[dict[str, object]] = []
        for event in out:
            mid = str(event.get("merchant_id", ""))
            if mid.startswith("MER_US") and rng.random() < 0.7:
                continue
            kept.append(event)
        return kept
    raise ValueError(f"unhandled payment fault {fault_id!r}")


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
