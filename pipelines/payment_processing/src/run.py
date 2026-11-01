"""Payment processing pipeline: several files, functions calling across them.

Shape: ``run`` is the only orchestrator. ``clean``, ``enrich``, and ``reconcile``
live in their own modules and share ``rules`` (status, cents-to-dollars, region).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from clean import clean
from enrich import enrich
from ingest import ingest
from reconcile import reconcile


def run(data_dir: Path) -> pd.DataFrame:
    """Full pipeline: ingest → clean → enrich → reconcile."""
    df = ingest(data_dir)
    df = clean(df)
    df = enrich(df)
    return reconcile(df)
