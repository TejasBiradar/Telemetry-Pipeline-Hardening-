"""The default fault scenarios the evaluation engine runs: one of each type in the
catalogue, each targeting a real `client_version` from `datagen.generate.VERSIONS`, plus one
clean run as the negative control.
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
    fault_type: FaultType  # known up front, without having to run `apply` first (e.g. for an API listing)
    apply: Apply


def default_scenarios(seed: int = 123, onset_batch: int = 4) -> list[FaultScenario]:
    rng = random.Random(seed)  # nosec B311 - synthetic test-data generation, not security-sensitive
    return [
        FaultScenario("unit_change_android", FaultType.UNIT_CHANGE,
                     lambda b: faults.inject_unit_change(b, onset_batch, "5.2.0")),
        FaultScenario("feed_stops_ios", FaultType.FEED_STOPS,
                     lambda b: faults.inject_feed_stops(b, onset_batch, "6.1.0")),
        FaultScenario("new_nullable_web", FaultType.NEW_NULLABLE,
                     lambda b: faults.inject_new_nullable(b, onset_batch, "1.5.2", rng)),
        FaultScenario("type_change_android", FaultType.TYPE_CHANGE,
                     lambda b: faults.inject_type_change(b, onset_batch, "5.1.3")),
        FaultScenario("gradual_drift_ios", FaultType.GRADUAL_DRIFT,
                     lambda b: faults.inject_gradual_drift(b, onset_batch, "6.0.1")),
        FaultScenario("text_change_web", FaultType.TEXT_CHANGE,
                     lambda b: faults.inject_text_change(b, onset_batch, "1.4.0", rng)),
        FaultScenario("volume_drop_android", FaultType.VOLUME_DROP,
                     lambda b: faults.inject_volume_drop(b, onset_batch, "5.2.0", rng)),
        FaultScenario("clean", FaultType.CLEAN, lambda b: faults.inject_clean(b)),
    ]
