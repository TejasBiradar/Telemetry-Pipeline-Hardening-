"""Runtime tracer: run the pipeline once and record what really flows between stages.

The pipeline module is loaded from its path and left untouched on disk. Each stage function
is wrapped in memory so the DataFrame it returns is snapshotted (columns, row counts, null
counts). Nothing is written to the pipeline.
"""

from __future__ import annotations

import functools
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd


@dataclass
class StageSnapshot:
    stage: str
    rows_in: int | None
    rows_out: int
    columns: list[str]
    new_columns: list[str]
    dropped_columns: list[str]
    null_counts: dict[str, int]


@dataclass
class RuntimeTrace:
    snapshots: list[StageSnapshot] = field(default_factory=list)
    error: str | None = None  # set if the pipeline raised; snapshots up to that point remain

    def observed_columns(self) -> set[str]:
        return {c for s in self.snapshots for c in s.columns}

    def columns_at(self, stage: str) -> list[str]:
        return next((s.columns for s in self.snapshots if s.stage == stage), [])

    def to_json(self) -> dict[str, Any]:
        return {"error": self.error, "stages": [s.__dict__ for s in self.snapshots]}


def load_module(path: Path, name: str = "pipeline_under_test") -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trace_pipeline(module: ModuleType, entry: str, stages: list[str],
                   *args: Any, **kwargs: Any) -> RuntimeTrace:
    """Run `module.<entry>(*args)` with every function in `stages` snapshotted."""
    trace = RuntimeTrace()
    previous: dict[str, StageSnapshot | None] = {"last": None}

    def wrap(name: str, func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*a: Any, **kw: Any) -> Any:
            result = func(*a, **kw)
            if isinstance(result, pd.DataFrame):
                last = previous["last"]
                before = set(last.columns) if last else set()
                snap = StageSnapshot(
                    stage=name,
                    rows_in=last.rows_out if last else None,
                    rows_out=len(result),
                    columns=list(result.columns),
                    new_columns=[c for c in result.columns if c not in before] if last else [],
                    dropped_columns=sorted(before - set(result.columns)),
                    null_counts={c: int(result[c].isna().sum()) for c in result.columns},
                )
                trace.snapshots.append(snap)
                previous["last"] = snap
            return result
        return wrapper

    originals = {s: getattr(module, s) for s in stages}
    for name, func in originals.items():
        setattr(module, name, wrap(name, func))
    try:
        getattr(module, entry)(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a crash is data about the pipeline
        trace.error = f"{type(exc).__name__}: {exc}"
    finally:
        for name, func in originals.items():
            setattr(module, name, func)
    return trace
