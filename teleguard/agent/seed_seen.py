"""Baseline existing stage outputs when monitoring starts for a stage.

Confirming a stage (or attaching a connector while stages are already confirmed)
must not backfill historical files into Results. Mark what is already in the
store as seen; only objects that appear afterward are checked. Existing result
rows for those historical keys are removed so the Results tab clears.
"""

from __future__ import annotations

import logging
from pathlib import Path

from teleguard.agent.db_source import read_table, table_fingerprint
from teleguard.agent.minio_client import list_objects
from teleguard.agent.results_store import delete_runs_for_object_keys
from teleguard.agent.seen_state import load_seen, mark_seen
from teleguard.onboard.code import (
    DEFAULT_STORE,
    CodeOnboardRecord,
    agent_checkpoints,
    confirmed_stages,
)
from teleguard.onboard.output_store import MinioOutputStore, parse_output_store

log = logging.getLogger(__name__)


def watch_baseline_key(stage: str) -> str:
    """Sentinel stored in agent_seen when a stage's historical baseline is taken."""
    return f"__watch_baseline__:{stage}"


def newly_confirmed_stages(
    before: CodeOnboardRecord,
    after: CodeOnboardRecord,
) -> list[str]:
    """Stages that flipped to confirmed between two record versions."""
    return [
        stage
        for stage in after.stages
        if after.stage_status.get(stage) == "confirmed"
        and before.stage_status.get(stage) != "confirmed"
    ]


def seed_existing_outputs(
    record: CodeOnboardRecord,
    *,
    stages: list[str] | None = None,
    store_root: Path = DEFAULT_STORE,
) -> int:
    """Mark current objects as seen and drop their stored check runs.

    Returns how many object keys were baselined. Listing failures are logged and
    skipped so a confirm request still succeeds.
    """
    store = parse_output_store(record.output_store)
    if store is None:
        return 0

    wanted = set(stages) if stages is not None else set(confirmed_stages(record))
    wanted &= set(confirmed_stages(record))
    if not wanted:
        return 0

    checkpoints = [
        cp for cp in agent_checkpoints(record) if cp.get("stage") in wanted
    ]
    if not checkpoints:
        return 0

    marked = 0
    for cp in checkpoints:
        stage = cp["stage"]
        location = cp.get("object_location") or store.stage_prefix(stage)
        try:
            keys = _current_keys(store, stage=stage, location=location)
            baseline_stage_outputs(
                record.pipeline_id,
                store,
                stage=stage,
                location=location,
                store_root=store_root,
                force=True,
            )
            marked += len(keys)
        except Exception as exc:  # noqa: BLE001 - confirm must not fail on list
            log.warning(
                "seed_seen skipped stage=%s pipeline=%s: %s",
                stage,
                record.pipeline_id,
                exc,
            )
    return marked


def baseline_stage_outputs(
    pipeline_id: str,
    store: MinioOutputStore,
    *,
    stage: str,
    location: str,
    store_root: Path = DEFAULT_STORE,
    force: bool = False,
) -> bool:
    """Ignore everything currently at ``location`` for ``stage``.

    Returns True when a baseline was taken (caller should skip checks this cycle).
    When ``force`` is false and the stage is already baselined, returns False.
    """
    sentinel = watch_baseline_key(stage)
    already = load_seen(pipeline_id, store_root=store_root)
    if not force and sentinel in already:
        return False

    keys = _current_keys(store, stage=stage, location=location)
    for key in keys:
        if key not in already:
            mark_seen(pipeline_id, key, store_root=store_root)
            already.add(key)
    if sentinel not in already:
        mark_seen(pipeline_id, sentinel, store_root=store_root)
        already.add(sentinel)
    removed = delete_runs_for_object_keys(pipeline_id, keys, store_root=store_root)
    log.info(
        "watch baseline stage=%s pipeline=%s keys=%s removed_runs=%s",
        stage,
        pipeline_id,
        len(keys),
        removed,
    )
    return True


def _current_keys(store: MinioOutputStore, *, stage: str, location: str) -> list[str]:
    if store.kind in {"database", "postgres"}:
        frame = read_table(store, location, stage=stage)
        return [f"db://{location}/{stage}#{table_fingerprint(frame)}"]
    return [
        obj.key
        for obj in list_objects(store, location)
        if _is_batch_file(obj.key)
    ]


def _is_batch_file(key: str) -> bool:
    lower = key.lower()
    return lower.endswith((".parquet", ".csv", ".json", ".jsonl"))
