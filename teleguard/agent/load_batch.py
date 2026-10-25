"""Load a downloaded stage dump into a DataFrame."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_batch_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=suffix == ".jsonl")
    raise ValueError(f"unsupported batch file type: {suffix or path.name}")
