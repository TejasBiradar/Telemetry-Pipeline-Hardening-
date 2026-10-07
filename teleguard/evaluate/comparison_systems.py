"""The two baselines every detection number is measured against (BUILD_PLAN.md ADR-10):
B0 (no checks at all) and B1 (the simplest thing a less careful team would ship). "Ours" is
the contract-driven system built elsewhere in this package.
"""

from __future__ import annotations

from collections.abc import Callable

from teleguard.checks.base import Check
from teleguard.checks.gates import SchemaCheck
from teleguard.contracts.factory import build_checks
from teleguard.contracts.model import Contract
from teleguard.drift.baseline import BaselineStore

ChecksFor = Callable[[str], list[Check]]


def b0_no_checks() -> ChecksFor:
    return lambda checkpoint: []


def b1_naive_schema_only() -> ChecksFor:
    """What a team in a hurry would actually ship: one dtype check, nothing segmented,
    no drift, no volume. Deliberately not "nothing" — a strawman nobody would build is not
    a fair comparison."""
    def checks_for(checkpoint: str) -> list[Check]:
        if checkpoint == "after_ingest":
            return [SchemaCheck(checkpoint, "duration_ms", "numeric")]
        return []
    return checks_for


def ours(contract: Contract, baselines: BaselineStore) -> ChecksFor:
    return lambda checkpoint: build_checks(contract, checkpoint, baselines)
