"""Per-pipeline fault scenarios for demos and evaluation.

Each catalogue targets fields/segments that pipeline actually ingests, so switching the
active pipeline changes which faults appear in the UI dropdown.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from teleguard.inject import faults
from teleguard.inject.faults import Batch, FaultType, Injection

Apply = Callable[[list[Batch]], tuple[list[Batch], Injection]]


@dataclass(frozen=True)
class FaultScenario:
    name: str
    fault_type: FaultType
    apply: Apply
    description: str = ""


def default_scenarios(seed: int = 123, onset_batch: int = 4) -> list[FaultScenario]:
    """Backward-compatible alias: web_analytics catalogue."""
    return scenarios_for_pipeline("web_analytics", seed=seed, onset_batch=onset_batch)


def scenarios_for_pipeline(
    pipeline_id: str, seed: int = 123, onset_batch: int = 4
) -> list[FaultScenario]:
    """Return fault scenarios aligned to ``pipeline_id``'s ingest schema."""
    if pipeline_id == "payment_processing":
        return _payment_scenarios(seed=seed, onset_batch=onset_batch)
    if pipeline_id == "user_behavior":
        return _user_behavior_scenarios(seed=seed, onset_batch=onset_batch)
    return _web_analytics_scenarios(seed=seed, onset_batch=onset_batch)


def _web_analytics_scenarios(seed: int, onset_batch: int) -> list[FaultScenario]:
    rng = random.Random(seed)  # nosec B311
    return [
        FaultScenario(
            "unit_change_android",
            FaultType.UNIT_CHANGE,
            lambda b: faults.inject_unit_change(b, onset_batch, "5.2.0"),
            "duration_ms arrives already in seconds for Android 5.2.0",
        ),
        FaultScenario(
            "feed_stops_ios",
            FaultType.FEED_STOPS,
            lambda b: faults.inject_feed_stops(b, onset_batch, "6.1.0"),
            "iOS 6.1.0 stops emitting events",
        ),
        FaultScenario(
            "new_nullable_web",
            FaultType.NEW_NULLABLE,
            lambda b: faults.inject_new_nullable(b, onset_batch, "1.5.2", rng),
            "web 1.5.2 starts sending null user_id",
        ),
        FaultScenario(
            "type_change_android",
            FaultType.TYPE_CHANGE,
            lambda b: faults.inject_type_change(b, onset_batch, "5.1.3"),
            "duration_ms becomes text like '1483ms' on Android 5.1.3",
        ),
        FaultScenario(
            "gradual_drift_ios",
            FaultType.GRADUAL_DRIFT,
            lambda b: faults.inject_gradual_drift(b, onset_batch, "6.0.1"),
            "duration_ms creeps upward each batch on iOS 6.0.1",
        ),
        FaultScenario(
            "text_change_web",
            FaultType.TEXT_CHANGE,
            lambda b: faults.inject_text_change(b, onset_batch, "1.4.0", rng),
            "new error_message templates on web 1.4.0",
        ),
        FaultScenario(
            "volume_drop_android",
            FaultType.VOLUME_DROP,
            lambda b: faults.inject_volume_drop(b, onset_batch, "5.2.0", rng),
            "Android 5.2.0 volume drops ~60%",
        ),
        FaultScenario(
            "clean",
            FaultType.CLEAN,
            lambda b: faults.inject_clean(b),
            "no fault — negative control",
        ),
    ]


def _user_behavior_scenarios(seed: int, onset_batch: int) -> list[FaultScenario]:
    """Same event shape as web_analytics; faults target session/engagement fields."""
    rng = random.Random(seed)  # nosec B311
    return [
        FaultScenario(
            "unit_change_android",
            FaultType.UNIT_CHANGE,
            lambda b: faults.inject_unit_change(b, onset_batch, "5.2.0"),
            "duration_ms already in seconds → session_duration_s collapses",
        ),
        FaultScenario(
            "new_nullable_web",
            FaultType.NEW_NULLABLE,
            lambda b: faults.inject_new_nullable(b, onset_batch, "1.5.2", rng),
            "null user_id spikes on web 1.5.2 (filter_sessions drops them)",
        ),
        FaultScenario(
            "type_change_android",
            FaultType.TYPE_CHANGE,
            lambda b: faults.inject_type_change(b, onset_batch, "5.1.3"),
            "duration_ms becomes non-numeric text on Android 5.1.3",
        ),
        FaultScenario(
            "action_flood_ios",
            FaultType.VOLUME_DROP,
            lambda b: faults.inject_volume_drop(b, onset_batch, "6.1.0", rng, drop_rate=0.7),
            "iOS 6.1.0 traffic drops — fewer page_view rows after filter",
        ),
        FaultScenario(
            "feed_stops_ios",
            FaultType.FEED_STOPS,
            lambda b: faults.inject_feed_stops(b, onset_batch, "6.0.1"),
            "iOS 6.0.1 feed goes silent",
        ),
        FaultScenario(
            "clean",
            FaultType.CLEAN,
            lambda b: faults.inject_clean(b),
            "no fault — negative control",
        ),
    ]


def _payment_scenarios(seed: int, onset_batch: int) -> list[FaultScenario]:
    rng = random.Random(seed)  # nosec B311
    return [
        FaultScenario(
            "unit_change_card",
            FaultType.UNIT_CHANGE,
            lambda b: faults.inject_unit_change(
                b, onset_batch, "card", field_name="amount_cents", factor=100.0,
                segment_key="payment_method", in_payload=False,
            ),
            "card amounts already in dollars under amount_cents → amount_usd wrong",
        ),
        FaultScenario(
            "type_change_card",
            FaultType.TYPE_CHANGE,
            lambda b: faults.inject_type_change(
                b, onset_batch, "card", field_name="amount_cents",
                segment_key="payment_method", in_payload=False, suffix="",
            ),
            "amount_cents arrives as text for card payments",
        ),
        FaultScenario(
            "new_nullable_wallet",
            FaultType.NEW_NULLABLE,
            lambda b: faults.inject_new_nullable(
                b, onset_batch, "wallet", rng, field_name="user_id",
                segment_key="payment_method", in_payload=False,
            ),
            "wallet payments start omitting user_id",
        ),
        FaultScenario(
            "invalid_status_ach",
            FaultType.TYPE_CHANGE,
            lambda b: faults.inject_invalid_enum(
                b, onset_batch, "ach", field_name="status", bad_value="chargeback",
                segment_key="payment_method",
            ),
            "ACH status becomes 'chargeback' (not in allowed set)",
        ),
        FaultScenario(
            "volume_drop_card",
            FaultType.VOLUME_DROP,
            lambda b: faults.inject_volume_drop(
                b, onset_batch, "card", rng, drop_rate=0.65,
                segment_key="payment_method",
            ),
            "card payment volume drops ~65%",
        ),
        FaultScenario(
            "feed_stops_wallet",
            FaultType.FEED_STOPS,
            lambda b: faults.inject_feed_stops(
                b, onset_batch, "wallet", segment_key="payment_method",
            ),
            "wallet method stops sending transactions",
        ),
        FaultScenario(
            "clean",
            FaultType.CLEAN,
            lambda b: faults.inject_clean(b),
            "no fault — negative control",
        ),
    ]
