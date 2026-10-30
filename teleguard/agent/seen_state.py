"""Track which MinIO objects the agent has already processed."""

from __future__ import annotations

import json
from pathlib import Path

from teleguard.onboard.code import DEFAULT_STORE


def _path(pipeline_id: str, store_root: Path = DEFAULT_STORE) -> Path:
    return store_root / pipeline_id / "agent_seen.json"


def load_seen(pipeline_id: str, store_root: Path = DEFAULT_STORE) -> set[str]:
    from teleguard.pg_store import load_seen as load_seen_rows
    from teleguard.pg_store import uses_database as database_store

    if database_store(store_root, DEFAULT_STORE):
        return load_seen_rows(pipeline_id)
    path = _path(pipeline_id, store_root)
    if not path.exists():
        return set()
    raw: object = json.loads(path.read_text())
    if isinstance(raw, list):
        return {str(x) for x in raw}
    return set()


def mark_seen(
    pipeline_id: str,
    key: str,
    store_root: Path = DEFAULT_STORE,
) -> None:
    from teleguard.pg_store import mark_seen as mark_seen_row
    from teleguard.pg_store import uses_database as database_store

    if database_store(store_root, DEFAULT_STORE):
        mark_seen_row(pipeline_id, key)
        return
    seen = load_seen(pipeline_id, store_root)
    seen.add(key)
    path = _path(pipeline_id, store_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen), indent=2) + "\n")
