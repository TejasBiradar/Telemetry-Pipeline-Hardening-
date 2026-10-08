"""Discover pipelines under ``pipelines/`` and load each with an on-the-fly code graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from teleguard.analyze import analyze_legacy
from teleguard.contracts.model import Contract, load_contract
from teleguard.pipeline_registry import PipelineMetadata, PipelineRegistry
from teleguard.tracer import load_module

# Optional per-pipeline metadata file (nothing pipeline-specific is hardcoded in the API).
META_FILENAME = "pipeline.yaml"
DEFAULT_SOURCE_DIR = "legacy"


def discover_pipeline_dirs(pipelines_root: Path) -> list[Path]:
    """Return child dirs that have analyzable source (``legacy/`` or configured ``source_dir``)."""
    if not pipelines_root.is_dir():
        return []
    found: list[Path] = []
    for path in sorted(pipelines_root.iterdir()):
        if not path.is_dir():
            continue
        meta = _read_meta(path)
        source = path / str(meta.get("source_dir", DEFAULT_SOURCE_DIR))
        if source.is_dir() and any(source.iterdir()):
            found.append(path)
    return found


def _read_meta(pipeline_dir: Path) -> dict[str, Any]:
    meta_path = pipeline_dir / META_FILENAME
    if not meta_path.exists():
        return {}
    data = yaml.safe_load(meta_path.read_text()) or {}
    if not isinstance(data, dict):
        raise TypeError(f"{meta_path}: expected a mapping")
    return data


def _load_decisions(pipeline_dir: Path) -> dict[str, Any]:
    path = pipeline_dir / "review" / "decisions.json"
    if not path.exists():
        return {}
    raw: object = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise TypeError(f"{path}: expected a JSON object")
    return raw


def source_root_for(pipeline_dir: Path, meta: dict[str, Any] | None = None) -> Path:
    """Resolve the directory that holds pipeline source code."""
    meta = meta if meta is not None else _read_meta(pipeline_dir)
    return pipeline_dir / str(meta.get("source_dir", DEFAULT_SOURCE_DIR))


def load_pipeline(pipeline_dir: Path) -> PipelineMetadata:
    """Load one pipeline: analyze source on the fly (never read a cached graph.json)."""
    pipeline_id = pipeline_dir.name
    meta = _read_meta(pipeline_dir)
    entry = str(meta.get("entry", "run.run"))
    adapter_name = meta.get("adapter")
    if adapter_name is not None:
        adapter_name = str(adapter_name)

    source_dir = source_root_for(pipeline_dir, meta)
    analysis, language = analyze_legacy(
        source_dir, entry=entry, adapter_name=adapter_name
    )

    contract: Contract | None = None
    contract_path = pipeline_dir / "contracts.yaml"
    if contract_path.exists():
        contract = load_contract(contract_path)

    name = str(meta.get("name", contract.pipeline if contract else pipeline_id))
    description = str(meta.get("description", ""))

    module_name = entry.rsplit(".", 1)[0]
    module_path = source_dir / f"{module_name}.py"
    legacy_module = load_module(module_path) if module_path.exists() else None

    metadata = PipelineMetadata(
        id=pipeline_id,
        name=name,
        description=description,
        source_root=pipeline_dir,
        adapter_name="sql" if language == "sql" else "python_pandas",
        entry_point=entry,
        contract=contract,
        analysis=analysis,
        findings_json=[f.to_json() for f in analysis.findings],
        decisions=_load_decisions(pipeline_dir),
        status="ready",
    )
    metadata._legacy_module = legacy_module  # type: ignore[attr-defined]
    metadata._baselines = None  # type: ignore[attr-defined]
    metadata._source_dir = source_dir  # type: ignore[attr-defined]
    return metadata


def build_registry(
    pipelines_root: Path,
    *,
    active_id: str | None = None,
) -> PipelineRegistry:
    """Discover every pipeline under ``pipelines_root`` and analyze each on the fly."""
    registry = PipelineRegistry()
    dirs = discover_pipeline_dirs(pipelines_root)
    if not dirs:
        raise FileNotFoundError(f"no pipelines with source under {pipelines_root}")

    marked_default: str | None = None
    for pipeline_dir in dirs:
        meta = _read_meta(pipeline_dir)
        loaded = load_pipeline(pipeline_dir)
        registry.add(loaded)
        if meta.get("default") is True and marked_default is None:
            marked_default = loaded.id

    if active_id and active_id in registry.pipelines:
        registry.select(active_id)
    elif marked_default is not None:
        registry.select(marked_default)
    else:
        registry.select(dirs[0].name)
    return registry
