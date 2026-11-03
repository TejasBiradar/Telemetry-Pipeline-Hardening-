"""Ad performance ETL: multi-file media pipeline with CPM and rollups.

Shape: ``run`` orchestrates ``ingest`` → ``clean`` → ``enrich`` → ``rollup``.
Shared formulas live in ``metrics.py``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from clean import clean
from enrich import enrich
from ingest import ingest
from rollup import rollup


def run(data_dir: Path) -> pd.DataFrame:
    """Full pipeline: ingest → clean → enrich → rollup."""
    df = ingest(data_dir)
    df = clean(df)
    df = enrich(df)
    return rollup(df)
