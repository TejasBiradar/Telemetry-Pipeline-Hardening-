"""Check interface. Every gate and drift detector in this package implements this.

Shared contract (CLAUDE.md rule 7): the `Check` protocol shape itself (not the individual
check classes) should not change without the team's agreement, since `guard.py` and the
contract loader both depend on it.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from teleguard.models import BatchContext, CheckResult, CheckType

# Below this many rows in a field/segment, pass/fail rates are statistical noise. Checks
# report `insufficient_data` instead of guessing (BUILD_PLAN.md §3.3 "tiny segments").
MIN_SAMPLE_SIZE = 30


class Check(Protocol):
    """A check never writes anywhere and never modifies `df` (CLAUDE.md rule 5)."""

    name: str
    check_type: CheckType

    def run(self, df: pd.DataFrame, ctx: BatchContext) -> list[CheckResult]: ...


def segments(df: pd.DataFrame, ctx: BatchContext) -> list[tuple[str | None, pd.DataFrame]]:
    """Split `df` by `ctx.segment_column`, or return it whole under segment `None`.

    A fault in one client version must not be averaged away by pooling every segment
    together (BUILD_PLAN.md §3.4 "hidden in the overall average" — the key point of this
    brief).
    """
    if not ctx.segment_column or ctx.segment_column not in df.columns:
        return [(None, df)]
    return [(str(key), part) for key, part in df.groupby(ctx.segment_column, dropna=False)]
