"""Map confirmed onboard guarantees to deterministic gate checks (agent hot path)."""

from __future__ import annotations

from typing import Any

from teleguard.checks.base import Check
from teleguard.checks.gates import NullRateCheck, SchemaCheck, VolumeCheck

_NULLISH_KINDS = frozenset(
    {
        "required_field",
        "null_lookalike_value",
        "group_key_drops_nulls",
    }
)


def checks_from_guarantees(checkpoint: str, guarantees: list[dict[str, Any]]) -> list[Check]:
    """Build a small check set from confirmed finding JSON objects.

    Always includes a volume floor so empty dumps fail. Per-field: schema (exists)
    plus null-rate for required/null-related kinds. Drift/unit need baselines — deferred.
    """
    checks: list[Check] = [VolumeCheck(checkpoint, min_rows=1, max_rows=None)]
    seen: set[str] = set()
    for g in guarantees:
        field = g.get("field")
        if not isinstance(field, str) or not field or field in seen:
            continue
        seen.add(field)
        checks.append(SchemaCheck(checkpoint, field))
        kind = str(g.get("kind", ""))
        if kind in _NULLISH_KINDS:
            checks.append(NullRateCheck(checkpoint, field, max_null_rate=0.0))
    return checks
