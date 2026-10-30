"""Postgres store for registration, review decisions, and agent results.

Used when ``STAGE_DATABASE_URL`` or ``DATABASE_URL`` is set and the caller is
writing the default store. Tests that pass a temporary directory keep files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

_MIGRATION = Path(__file__).resolve().parents[1] / "db" / "migrations" / "002_runtime_store.sql"
_ready = False
_legacy_imported = False


def database_url() -> str:
    """DSN for the demo database. Empty when the process should keep local files."""
    return os.environ.get("STAGE_DATABASE_URL", "").strip() or os.environ.get("DATABASE_URL", "").strip()


def uses_database(store_root: Path, default_store: Path) -> bool:
    """True when this store root is the product default and a DSN is configured."""
    if not database_url():
        return False
    return store_root.resolve() == default_store.resolve()


def connect() -> psycopg.Connection[tuple[Any, ...]]:
    dsn = database_url()
    if not dsn:
        raise RuntimeError("STAGE_DATABASE_URL is not set")
    conn = psycopg.connect(dsn)
    _ensure_schema(conn)
    return conn


def save_registration(document: dict[str, Any]) -> str:
    """Upsert one onboard record and replace its stage, guarantee, and checkpoint rows."""
    pipeline_id = str(document["pipeline_id"])
    with connect() as conn:
        _upsert_registration(conn, document)
        conn.commit()
    return f"db://registered_pipelines/{pipeline_id}"


def load_registration(pipeline_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT document FROM registered_pipelines WHERE pipeline_id = %s",
            (pipeline_id,),
        ).fetchone()
    if row is None:
        return None
    document = row[0]
    if not isinstance(document, dict):
        raise TypeError(f"registered_pipelines {pipeline_id}: expected a JSON object")
    return document


def list_registrations() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT document FROM registered_pipelines ORDER BY pipeline_id",
        ).fetchall()
    documents: list[dict[str, Any]] = []
    for row in rows:
        document = row[0]
        if isinstance(document, dict):
            documents.append(document)
    return documents


def append_agent_run(document: dict[str, Any]) -> None:
    """Append one agent run and one check_alerts row per result."""
    results = document.get("results", [])
    if not isinstance(results, list):
        results = []
    with connect() as conn:
        inserted = conn.execute(
            "INSERT INTO agent_runs "
            "(pipeline_id, stage, checkpoint, object_key, batch_id, observed_at, "
            "failed, passed, results, document) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                str(document["pipeline_id"]),
                str(document.get("stage", "")),
                str(document.get("checkpoint", "")),
                str(document.get("object_key", "")),
                str(document.get("batch_id", "")),
                str(document.get("observed_at", "")),
                int(document.get("failed", 0)),
                int(document.get("passed", 0)),
                Jsonb(results),
                Jsonb(document),
            ),
        ).fetchone()
        if inserted is None:
            raise RuntimeError("agent run insert did not return an id")
        run_id = int(inserted[0])
        for item in results:
            if not isinstance(item, dict):
                continue
            field = item.get("field")
            conn.execute(
                "INSERT INTO check_alerts "
                "(pipeline_id, run_id, stage, checkpoint, batch_id, observed_at, "
                "check_name, status, field_name, message, detail) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    str(document["pipeline_id"]),
                    run_id,
                    str(document.get("stage", "")),
                    str(item.get("checkpoint", document.get("checkpoint", ""))),
                    str(document.get("batch_id", "")),
                    str(document.get("observed_at", "")),
                    str(item.get("check", "")),
                    str(item.get("status", "")),
                    None if field is None else str(field),
                    str(item.get("message", "")),
                    Jsonb(item),
                ),
            )
        conn.commit()


def list_agent_runs(pipeline_id: str, *, limit: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT document FROM ("
            "SELECT id, document FROM agent_runs WHERE pipeline_id = %s "
            "ORDER BY id DESC LIMIT %s"
            ") recent ORDER BY id ASC",
            (pipeline_id, limit),
        ).fetchall()
    documents: list[dict[str, Any]] = []
    for row in rows:
        document = row[0]
        if isinstance(document, dict):
            documents.append(document)
    return documents


def load_seen(pipeline_id: str) -> set[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT object_key FROM agent_seen_objects WHERE pipeline_id = %s",
            (pipeline_id,),
        ).fetchall()
    return {str(row[0]) for row in rows}


def mark_seen(pipeline_id: str, object_key: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO agent_seen_objects (pipeline_id, object_key) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (pipeline_id, object_key),
        )
        conn.commit()


def save_notify(email: str, pipeline_id: str, source_note: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO notify_onboard (id, email, pipeline_id, source_note) "
            "VALUES (1, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET "
            "email = EXCLUDED.email, pipeline_id = EXCLUDED.pipeline_id, "
            "source_note = EXCLUDED.source_note",
            (email, pipeline_id, source_note),
        )
        conn.commit()


def load_notify() -> dict[str, str] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT email, pipeline_id, source_note FROM notify_onboard WHERE id = 1",
        ).fetchone()
    if row is None:
        return None
    return {"email": str(row[0]), "pipeline_id": str(row[1]), "source_note": str(row[2])}


def save_review_decisions(pipeline_id: str, decisions: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM review_decisions WHERE pipeline_id = %s", (pipeline_id,))
        for guarantee_id, raw in decisions.items():
            detail = dict(raw) if isinstance(raw, dict) else {"status": str(raw)}
            status = str(detail.get("status", "pending"))
            conn.execute(
                "INSERT INTO review_decisions (pipeline_id, guarantee_id, status, detail) "
                "VALUES (%s, %s, %s, %s)",
                (pipeline_id, str(guarantee_id), status, Jsonb(detail)),
            )
        conn.commit()


def load_review_decisions(pipeline_id: str) -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT guarantee_id, detail FROM review_decisions WHERE pipeline_id = %s",
            (pipeline_id,),
        ).fetchall()
    decisions: dict[str, Any] = {}
    for guarantee_id, detail in rows:
        if isinstance(detail, dict):
            decisions[str(guarantee_id)] = detail
        else:
            decisions[str(guarantee_id)] = {"status": "pending"}
    return decisions


def import_legacy_files(store_root: Path, notify_path: Path) -> None:
    """Copy existing JSON stores into Postgres once. Later writes stay in Postgres."""
    global _legacy_imported
    if _legacy_imported:
        return
    if store_root.is_dir():
        for child in sorted(store_root.iterdir()):
            meta = child / "metadata.json"
            if not child.is_dir() or not meta.is_file():
                continue
            raw: object = json.loads(meta.read_text())
            if not isinstance(raw, dict):
                continue
            pipeline_id = str(raw.get("pipeline_id", ""))
            if not pipeline_id or load_registration(pipeline_id) is not None:
                continue
            save_registration(raw)
            _import_runs(child / "agent_runs.jsonl")
            _import_seen(pipeline_id, child / "agent_seen.json")
    if notify_path.is_file() and load_notify() is None:
        raw_notify: object = json.loads(notify_path.read_text())
        if isinstance(raw_notify, dict):
            email = str(raw_notify.get("email", "")).strip()
            pipeline_id = str(raw_notify.get("pipeline_id", "")).strip()
            if email and pipeline_id:
                save_notify(email, pipeline_id, str(raw_notify.get("source_note", "")))
    _legacy_imported = True


def _import_runs(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        raw: object = json.loads(line)
        if isinstance(raw, dict):
            append_agent_run(raw)


def _import_seen(pipeline_id: str, path: Path) -> None:
    if not path.is_file():
        return
    raw: object = json.loads(path.read_text())
    if not isinstance(raw, list):
        return
    for key in raw:
        mark_seen(pipeline_id, str(key))


def _upsert_registration(conn: psycopg.Connection[tuple[Any, ...]], document: dict[str, Any]) -> None:
    pipeline_id = str(document["pipeline_id"])
    output_store = document.get("output_store")
    graph = document.get("graph", {"nodes": [], "edges": []})
    conn.execute(
        "INSERT INTO registered_pipelines "
        "(pipeline_id, name, description, entry, adapter, source_path, git_url, git_ref, "
        "source_subdir, analyzed_at, output_store, graph, document, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()) "
        "ON CONFLICT (pipeline_id) DO UPDATE SET "
        "name = EXCLUDED.name, description = EXCLUDED.description, entry = EXCLUDED.entry, "
        "adapter = EXCLUDED.adapter, source_path = EXCLUDED.source_path, "
        "git_url = EXCLUDED.git_url, git_ref = EXCLUDED.git_ref, "
        "source_subdir = EXCLUDED.source_subdir, analyzed_at = EXCLUDED.analyzed_at, "
        "output_store = EXCLUDED.output_store, graph = EXCLUDED.graph, "
        "document = EXCLUDED.document, updated_at = NOW()",
        (
            pipeline_id,
            str(document.get("name", "")),
            str(document.get("description", "")),
            str(document.get("entry", "")),
            str(document.get("adapter", "")),
            str(document.get("source_path", "")),
            str(document.get("git_url", "")),
            str(document.get("git_ref", "")),
            str(document.get("source_subdir", "")),
            str(document.get("analyzed_at", "")),
            Jsonb(output_store) if isinstance(output_store, dict) else None,
            Jsonb(graph if isinstance(graph, dict) else {}),
            Jsonb(document),
        ),
    )
    conn.execute("DELETE FROM registered_stages WHERE pipeline_id = %s", (pipeline_id,))
    conn.execute("DELETE FROM registered_guarantees WHERE pipeline_id = %s", (pipeline_id,))
    conn.execute("DELETE FROM registered_checkpoints WHERE pipeline_id = %s", (pipeline_id,))
    stages = [str(item) for item in document.get("stages", [])]
    stage_ids = [str(item) for item in document.get("stage_ids", [])]
    stage_status = document.get("stage_status", {})
    if not isinstance(stage_status, dict):
        stage_status = {}
    for position, label in enumerate(stages):
        stage_id = stage_ids[position] if position < len(stage_ids) else ""
        conn.execute(
            "INSERT INTO registered_stages (pipeline_id, position, stage_label, stage_id, status) "
            "VALUES (%s, %s, %s, %s, %s)",
            (pipeline_id, position, label, stage_id, str(stage_status.get(label, "pending"))),
        )
    guarantee_status = document.get("guarantee_status", {})
    if not isinstance(guarantee_status, dict):
        guarantee_status = {}
    findings = document.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            guarantee_id = str(finding.get("id", ""))
            if not guarantee_id:
                continue
            evidence = finding.get("evidence")
            file_path = ""
            line_no = 0
            if isinstance(evidence, dict):
                file_path = str(evidence.get("file", ""))
                line_no = int(evidence.get("line") or 0)
            field = finding.get("field")
            conn.execute(
                "INSERT INTO registered_guarantees "
                "(pipeline_id, guarantee_id, status, kind, field_name, message, file_path, line_no) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    pipeline_id,
                    guarantee_id,
                    str(guarantee_status.get(guarantee_id, "pending")),
                    str(finding.get("kind", "")),
                    None if field is None else str(field),
                    str(finding.get("message", "")),
                    file_path,
                    line_no,
                ),
            )
    checkpoints = document.get("checkpoints", [])
    if isinstance(checkpoints, list):
        for item in checkpoints:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", ""))
            if not name:
                continue
            conn.execute(
                "INSERT INTO registered_checkpoints "
                "(pipeline_id, name, after_stage, attach, location) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    pipeline_id,
                    name,
                    str(item.get("after_stage", "")),
                    str(item.get("attach", "")),
                    str(item.get("location", "")),
                ),
            )


def _ensure_schema(conn: psycopg.Connection[tuple[Any, ...]]) -> None:
    global _ready
    if _ready:
        return
    script = _MIGRATION.read_text()
    for statement in _statements(script):
        conn.execute(statement)
    conn.commit()
    _ready = True


def _statements(script: str) -> list[str]:
    statements: list[str] = []
    for chunk in script.split(";"):
        lines = [line for line in chunk.splitlines() if line.strip() and not line.strip().startswith("--")]
        statement = "\n".join(lines).strip()
        if statement:
            statements.append(statement)
    return statements
