"""Shared rules used by more than one payment stage."""

from __future__ import annotations

import pandas as pd

_ALLOWED_STATUS = frozenset({"settled", "declined", "pending", "refunded"})


def allowed_status() -> frozenset[str]:
    """Status values clean keeps and reconcile counts."""
    return _ALLOWED_STATUS


def to_usd(amount_cents: pd.Series) -> pd.Series:
    """Convert cents to dollars. Callers assume the column is still in cents."""
    return amount_cents / 100.0


def flag_error(messages: pd.Series) -> pd.Series:
    """True when the processor text mentions an error."""
    return messages.notna() & messages.str.contains("error", case=False, na=False)


def merchant_region(merchant_id: object) -> str:
    """Map a merchant id prefix to a region label."""
    mid = str(merchant_id)
    if mid.startswith("MER_US"):
        return "North America"
    if mid.startswith("MER_EU"):
        return "Europe"
    if mid.startswith("MER_APAC"):
        return "Asia Pacific"
    return "Other"


def is_declined(status: object) -> bool:
    """True for the declined status reconcile uses in its rate."""
    return status == "declined"
