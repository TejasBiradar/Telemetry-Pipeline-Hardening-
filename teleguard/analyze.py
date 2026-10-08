"""Shared static analysis entry: pick an adapter and build a code graph for a legacy tree."""

from __future__ import annotations

from pathlib import Path

from teleguard.adapters.base import AnalysisResult
from teleguard.adapters.python_pandas import PythonPandasAdapter
from teleguard.adapters.sql import SQLAdapter


def analyze_legacy(
    legacy: Path,
    *,
    entry: str = "run.run",
    adapter_name: str | None = None,
) -> tuple[AnalysisResult, str]:
    """Analyze `legacy/` and return (result, adapter language tag: \"python\" | \"sql\").

    Adapter selection:
    - explicit `adapter_name` wins when provided
    - else prefer SQL when the tree has only `.sql` files
    - else Python when any `.py` exists
    """
    has_py = any(legacy.rglob("*.py"))
    has_sql = any(legacy.rglob("*.sql"))
    chosen = adapter_name
    if chosen is None:
        if has_py and has_sql:
            # Mixed trees: Python adapter covers pandas stages; SQL files are ignored.
            chosen = "python_pandas"
        elif has_py:
            chosen = "python_pandas"
        elif has_sql:
            chosen = "sql"
        else:
            raise FileNotFoundError(f"no .py or .sql files found in {legacy}")

    if chosen == "python_pandas":
        return PythonPandasAdapter(entry=entry).analyze(legacy), "python"
    if chosen == "sql":
        return SQLAdapter().analyze(legacy), "sql"
    raise ValueError(f"unknown adapter: {chosen}")
