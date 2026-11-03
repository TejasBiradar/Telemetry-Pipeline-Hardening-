"""Shared media formulas used by enrich and rollup."""

from __future__ import annotations

import pandas as pd


def cpm(spend_usd: pd.Series, impressions: pd.Series) -> pd.Series:
    """Cost per thousand impressions."""
    return spend_usd / impressions * 1000.0


def cpc(spend_usd: pd.Series, clicks: pd.Series) -> pd.Series:
    """Cost per click."""
    return spend_usd / clicks


def ctr(clicks: pd.Series, impressions: pd.Series) -> pd.Series:
    """Click-through rate."""
    return clicks / impressions


def allowed_channels() -> frozenset[str]:
    return frozenset({"search", "social", "display", "video"})
