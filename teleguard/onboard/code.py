"""Code onboarding: analyze client source, store derived metadata only.

Supports a local directory or a git remote URL (shallow clone, then discard).
The product keeps metadata under ``data/onboarded/<pipeline_id>/``, not a
permanent source tree.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from teleguard.adapters.base import AnalysisResult, AttachMode, Checkpoint
from teleguard.analyze import analyze_legacy
from teleguard.codegraph.model import (
    CodeGraph,
    Edge,
    EdgeType,
    Evidence,
    Node,
    NodeType,
    Origin,
)
from teleguard.findings import Finding, FindingKind
from teleguard.onboard.git_source import shallow_clone
from teleguard.onboard.output_store import MinioOutputStore, parse_output_store
from teleguard.pipeline_registry import PipelineMetadata, PipelineRegistry

DEFAULT_STORE = Path(__file__).resolve().parents[2] / "data" / "onboarded"
DECISION_STATUSES = frozenset({"pending", "confirmed", "rejected"})


@dataclass(frozen=True)
class CodeOnboardRecord:
    """Derived understanding of a client pipeline (no permanent source tree)."""

    pipeline_id: str
    name: str
    description: str
    entry: str
    adapter: str
    source_path: str
    git_url: str
    git_ref: str
    source_subdir: str
    analyzed_at: str
    stages: list[str]
    checkpoints: list[dict[str, str]]
    findings: list[dict[str, Any]]
    graph: dict[str, Any]
    stage_ids: list[str]
    stage_status: dict[str, str]  # stage label -> pending|confirmed|rejected
    guarantee_status: dict[str, str]  # finding id -> pending|confirmed|rejected
    output_store: dict[str, Any] | None = None  # MinIO root; see output_store.py

    def to_json(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "name": self.name,
            "description": self.description,
            "entry": self.entry,
            "adapter": self.adapter,
            "source_path": self.source_path,
            "git_url": self.git_url,
            "git_ref": self.git_ref,
            "source_subdir": self.source_subdir,
            "analyzed_at": self.analyzed_at,
            "stages": self.stages,
            "checkpoints": self.checkpoints,
            "findings": self.findings,
            "graph": self.graph,
            "stage_ids": self.stage_ids,
            "stage_status": self.stage_status,
            "guarantee_status": self.guarantee_status,
            "output_store": self.output_store,
        }

    @staticmethod
    def from_json(raw: dict[str, Any]) -> CodeOnboardRecord:
        findings = list(raw.get("findings", []))
        guarantee_status = {
            str(k): str(v) for k, v in dict(raw.get("guarantee_status", {})).items()
        }
        # Older metadata: default every finding to pending.
        for finding in findings:
            if isinstance(finding, dict):
                fid = str(finding.get("id", ""))
                if fid and fid not in guarantee_status:
                    guarantee_status[fid] = "pending"
        store_raw = raw.get("output_store")
        output_store = dict(store_raw) if isinstance(store_raw, dict) else None
        return CodeOnboardRecord(
            pipeline_id=str(raw["pipeline_id"]),
            name=str(raw["name"]),
            description=str(raw.get("description", "")),
            entry=str(raw["entry"]),
            adapter=str(raw["adapter"]),
            source_path=str(raw.get("source_path", "")),
            git_url=str(raw.get("git_url", "")),
            git_ref=str(raw.get("git_ref", "")),
            source_subdir=str(raw.get("source_subdir", "")),
            analyzed_at=str(raw["analyzed_at"]),
            stages=[str(s) for s in raw.get("stages", [])],
            checkpoints=list(raw.get("checkpoints", [])),
            findings=findings,
            graph=dict(raw.get("graph", {"nodes": [], "edges": []})),
            stage_ids=[str(s) for s in raw.get("stage_ids", [])],
            stage_status={str(k): str(v) for k, v in dict(raw.get("stage_status", {})).items()},
            guarantee_status=guarantee_status,
            output_store=output_store,
        )


def generate_pipeline_id() -> str:
    """Allocate a new opaque pipeline id (UUID4 string)."""
    return str(uuid.uuid4())


def validate_pipeline_id(pipeline_id: str) -> str:
    """Accept only UUID strings (used when loading stored records)."""
    try:
        return str(UUID(pipeline_id))
    except ValueError as exc:
        raise ValueError("pipeline_id must be a UUID") from exc


def onboard_from_source(
    source_path: Path,
    *,
    name: str,
    entry: str = "run.run",
    adapter: str | None = None,
    description: str = "",
    pipeline_id: str | None = None,
) -> CodeOnboardRecord:
    """Analyze a local client directory (no git)."""
    return onboard_pipeline(
        name=name,
        entry=entry,
        adapter=adapter,
        description=description,
        pipeline_id=pipeline_id,
        source_path=source_path,
    )


def onboard_pipeline(
    *,
    name: str,
    entry: str = "run.run",
    adapter: str | None = None,
    description: str = "",
    pipeline_id: str | None = None,
    source_path: Path | None = None,
    git_url: str | None = None,
    git_ref: str = "HEAD",
    source_subdir: str = "",
) -> CodeOnboardRecord:
    """Analyze local path or git remote; return metadata only.

    Exactly one of ``source_path`` or ``git_url`` must be set. For git, a shallow
    clone is created, analyzed, then deleted — only URL/ref are stored.
    """
    if (source_path is None) == (git_url is None or not str(git_url).strip()):
        raise ValueError("provide exactly one of source_path or git_url")

    pid = validate_pipeline_id(pipeline_id) if pipeline_id else generate_pipeline_id()
    cleanup: Path | None = None
    stored_source = ""
    stored_git = ""
    stored_ref = ""
    stored_sub = source_subdir.strip()

    try:
        if git_url is not None and str(git_url).strip():
            checkout = shallow_clone(
                str(git_url),
                git_ref=git_ref,
                source_subdir=source_subdir,
            )
            cleanup = checkout.cleanup_dir
            root = checkout.analyze_root
            stored_git = str(git_url).strip()
            stored_ref = (git_ref.strip() or "HEAD")
            stored_source = ""  # ephemeral clone discarded
        else:
            assert source_path is not None
            root = source_path.resolve()
            if not root.is_dir():
                raise FileNotFoundError(f"source path is not a directory: {root}")
            stored_source = str(root)

        analysis, language = analyze_legacy(root, entry=entry, adapter_name=adapter)
    finally:
        if cleanup is not None:
            shutil.rmtree(cleanup, ignore_errors=True)

    adapter_name = "sql" if language == "sql" else "python_pandas"
    stage_labels = [analysis.graph.node(s).label for s in analysis.stages]
    checkpoints = [
        {
            "name": c.name,
            "after_stage": c.after_stage,
            "attach": c.attach.value,
            "location": c.location,
        }
        for c in analysis.checkpoints
    ]
    findings_json = [f.to_json() for f in analysis.findings]
    return CodeOnboardRecord(
        pipeline_id=pid,
        name=name,
        description=description,
        entry=entry,
        adapter=adapter_name,
        source_path=stored_source,
        git_url=stored_git,
        git_ref=stored_ref,
        source_subdir=stored_sub,
        analyzed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        stages=stage_labels,
        checkpoints=checkpoints,
        findings=findings_json,
        graph=analysis.graph.to_json(),
        stage_ids=list(analysis.stages),
        stage_status={label: "pending" for label in stage_labels},
        guarantee_status={str(f["id"]): "pending" for f in findings_json},
    )


def save_record(record: CodeOnboardRecord, store_root: Path = DEFAULT_STORE) -> str:
    """Persist metadata in Postgres, or under ``store_root`` when no database is configured."""
    if _use_database(store_root):
        from teleguard.pg_store import import_legacy_files, save_registration

        import_legacy_files(DEFAULT_STORE, _notify_path())
        return save_registration(record.to_json())
    dest = store_root / record.pipeline_id
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "metadata.json"
    path.write_text(json.dumps(record.to_json(), indent=2) + "\n")
    return str(path)


def load_record(pipeline_id: str, store_root: Path = DEFAULT_STORE) -> CodeOnboardRecord | None:
    if _use_database(store_root):
        from teleguard.pg_store import import_legacy_files, load_registration

        import_legacy_files(DEFAULT_STORE, _notify_path())
        raw = load_registration(pipeline_id)
        return CodeOnboardRecord.from_json(raw) if raw is not None else None
    path = store_root / pipeline_id / "metadata.json"
    if not path.exists():
        return None
    raw_file: object = json.loads(path.read_text())
    if not isinstance(raw_file, dict):
        raise TypeError(f"{path}: expected a JSON object")
    return CodeOnboardRecord.from_json(raw_file)


def list_records(store_root: Path = DEFAULT_STORE) -> list[CodeOnboardRecord]:
    if _use_database(store_root):
        from teleguard.pg_store import import_legacy_files, list_registrations

        import_legacy_files(DEFAULT_STORE, _notify_path())
        return [CodeOnboardRecord.from_json(item) for item in list_registrations()]
    if not store_root.is_dir():
        return []
    out: list[CodeOnboardRecord] = []
    for child in sorted(store_root.iterdir()):
        meta = child / "metadata.json"
        if child.is_dir() and meta.exists():
            raw: object = json.loads(meta.read_text())
            if isinstance(raw, dict):
                out.append(CodeOnboardRecord.from_json(raw))
    return out


def _use_database(store_root: Path) -> bool:
    from teleguard.pg_store import uses_database

    return uses_database(store_root, DEFAULT_STORE)


def _notify_path() -> Path:
    from teleguard.notify.onboard import DEFAULT_PATH

    return DEFAULT_PATH


def analysis_from_record(record: CodeOnboardRecord) -> AnalysisResult:
    """Rebuild an ``AnalysisResult`` from stored metadata (no source re-read)."""
    graph = _graph_from_json(record.graph)
    findings = [_finding_from_json(f) for f in record.findings]
    checkpoints = [
        Checkpoint(
            name=str(c["name"]),
            after_stage=str(c["after_stage"]),
            attach=AttachMode(str(c["attach"])),
            location=str(c["location"]),
        )
        for c in record.checkpoints
    ]
    return AnalysisResult(
        graph=graph,
        findings=findings,
        stages=list(record.stage_ids),
        checkpoints=checkpoints,
    )


def metadata_to_pipeline(record: CodeOnboardRecord) -> PipelineMetadata:
    """Turn an onboard record into a registry entry."""
    analysis = analysis_from_record(record)
    root = Path(record.source_path) if record.source_path else Path(".")
    decisions = {
        fid: {"status": status} for fid, status in record.guarantee_status.items()
    }
    return PipelineMetadata(
        id=record.pipeline_id,
        name=record.name,
        description=record.description,
        source_root=root,
        adapter_name=record.adapter,
        entry_point=record.entry,
        analysis=analysis,
        findings_json=list(record.findings),
        decisions=decisions,
        status="ready",
    )


def validate_decision_status(status: str) -> str:
    if status not in DECISION_STATUSES:
        raise ValueError(
            f"invalid status '{status}'; expected one of {sorted(DECISION_STATUSES)}"
        )
    return status


def set_stage_decision(
    record: CodeOnboardRecord,
    stage: str,
    status: str,
) -> CodeOnboardRecord:
    """Confirm/reject/reset one discovered stage."""
    validate_decision_status(status)
    if stage not in record.stages:
        raise KeyError(f"unknown stage: {stage}")
    updated = dict(record.stage_status)
    updated[stage] = status
    return replace(record, stage_status=updated)


def set_stage_decisions(
    record: CodeOnboardRecord,
    decisions: dict[str, str],
) -> CodeOnboardRecord:
    """Apply many stage decisions; unknown stage names raise ``KeyError``."""
    out = record
    for stage, status in decisions.items():
        out = set_stage_decision(out, stage, status)
    return out


def set_guarantee_decision(
    record: CodeOnboardRecord,
    guarantee_id: str,
    status: str,
) -> CodeOnboardRecord:
    """Confirm/reject/reset one finding (guarantee)."""
    validate_decision_status(status)
    known = {str(f.get("id", "")) for f in record.findings if isinstance(f, dict)}
    if guarantee_id not in known:
        raise KeyError(f"unknown guarantee: {guarantee_id}")
    updated = dict(record.guarantee_status)
    updated[guarantee_id] = status
    return replace(record, guarantee_status=updated)


def confirmed_stages(record: CodeOnboardRecord) -> list[str]:
    """Stage labels approved for the watcher agent (order preserved)."""
    return [s for s in record.stages if record.stage_status.get(s) == "confirmed"]


def confirmed_guarantees(record: CodeOnboardRecord) -> list[dict[str, Any]]:
    """Findings marked confirmed (rules the agent should enforce)."""
    return [
        f
        for f in record.findings
        if isinstance(f, dict)
        and record.guarantee_status.get(str(f.get("id", ""))) == "confirmed"
    ]


def set_output_store(
    record: CodeOnboardRecord,
    store: MinioOutputStore | dict[str, Any],
) -> CodeOnboardRecord:
    """Attach the client's one MinIO root (fixed ``{prefix}/{stage}/`` layout)."""
    parsed = store if isinstance(store, MinioOutputStore) else MinioOutputStore.from_json(store)
    return replace(record, output_store=parsed.to_json())


def clear_output_store(record: CodeOnboardRecord) -> CodeOnboardRecord:
    return replace(record, output_store=None)


def agent_checkpoints(record: CodeOnboardRecord) -> list[dict[str, str]]:
    """Checkpoints for confirmed stages, with MinIO URIs when an output store is set.

    Layout: ``s3://{bucket}/{prefix}/{stage}/``.
    """
    confirmed = set(confirmed_stages(record))
    if not confirmed:
        return []
    store = parse_output_store(record.output_store)
    if store is not None and store.stages:
        return _explicit_checkpoints(record, store, confirmed)
    # Map stage node id -> label for checkpoint.after_stage matching.
    id_to_label = {
        sid: record.stages[i]
        for i, sid in enumerate(record.stage_ids)
        if i < len(record.stages)
    }
    out: list[dict[str, str]] = []
    for cp in record.checkpoints:
        after = str(cp.get("after_stage", ""))
        label = id_to_label.get(after, after)
        stage = label if label in confirmed else (after if after in confirmed else "")
        if not stage:
            continue
        row = {
            "name": str(cp.get("name", "")),
            "stage": stage,
            "attach": str(cp.get("attach", "")),
            "location": str(cp.get("location", "")),
        }
        if store is not None:
            row["output_uri"] = store.stage_uri(stage)
            row["object_location"] = store.stage_prefix(stage)
        out.append(row)
    # If adapter checkpoints don't line up, still expose confirmed stages.
    if not out:
        for s in confirmed_stages(record):
            row = {
                "name": f"after_{s}",
                "stage": s,
                "attach": AttachMode.OUT_OF_PROCESS_TAP.value,
                "location": "",
            }
            if store is not None:
                row["output_uri"] = store.stage_uri(s)
                row["object_location"] = store.stage_prefix(s)
            out.append(row)
    return out


def _explicit_checkpoints(
    record: CodeOnboardRecord,
    store: MinioOutputStore,
    confirmed: set[str],
) -> list[dict[str, str]]:
    """Watch only the locations the client typed for confirmed stages."""
    out: list[dict[str, str]] = []
    for item in store.stages:
        if item.stage not in confirmed:
            continue
        out.append(
            {
                "name": f"after_{item.stage}",
                "stage": item.stage,
                "attach": AttachMode.OUT_OF_PROCESS_TAP.value,
                "location": "",
                "object_location": item.location,
                "output_uri": store.describe(item.location),
            }
        )
    return out


def register_record(registry: PipelineRegistry, record: CodeOnboardRecord) -> PipelineMetadata:
    """Add or replace the pipeline in the live registry."""
    meta = metadata_to_pipeline(record)
    registry.add(meta)
    return meta


def load_onboarded_into_registry(
    registry: PipelineRegistry,
    store_root: Path = DEFAULT_STORE,
) -> list[str]:
    """Load all saved onboard records into ``registry``. Returns loaded ids."""
    loaded: list[str] = []
    for record in list_records(store_root):
        register_record(registry, record)
        loaded.append(record.pipeline_id)
    return loaded


def _graph_from_json(data: dict[str, Any]) -> CodeGraph:
    graph = CodeGraph()
    for raw in data.get("nodes", []):
        if not isinstance(raw, dict):
            continue
        origin = Origin(str(raw.get("origin", Origin.STATIC.value)))
        graph.add_node(
            Node(
                id=str(raw["id"]),
                type=NodeType(str(raw["type"])),
                label=str(raw["label"]),
                attrs=dict(raw.get("attrs", {})),
                origin=origin,
            )
        )
    for raw in data.get("edges", []):
        if not isinstance(raw, dict):
            continue
        evidence = None
        ev = raw.get("evidence")
        if isinstance(ev, dict):
            evidence = Evidence(
                file=str(ev.get("file", "")),
                line=int(ev.get("line", 0)),
                snippet=str(ev.get("snippet", "")),
            )
        graph.add_edge(
            Edge(
                source=str(raw["source"]),
                target=str(raw["target"]),
                type=EdgeType(str(raw["type"])),
                evidence=evidence,
                attrs=dict(raw.get("attrs", {})),
                origin=Origin(str(raw.get("origin", Origin.STATIC.value))),
            )
        )
    return graph


def _finding_from_json(raw: dict[str, Any]) -> Finding:
    ev = raw.get("evidence", {})
    if not isinstance(ev, dict):
        ev = {}
    field_raw = raw.get("field")
    field = None if field_raw is None else str(field_raw)
    return Finding(
        kind=FindingKind(str(raw["kind"])),
        field=field,
        message=str(raw["message"]),
        evidence=Evidence(
            file=str(ev.get("file", "")),
            line=int(ev.get("line", 0)),
            snippet=str(ev.get("snippet", "")),
        ),
    )
