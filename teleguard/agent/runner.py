"""Watcher agent: poll MinIO stage folders → run checks → report to API or local store."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from urllib import error, request

from teleguard.agent.db_source import read_table, table_fingerprint
from teleguard.agent.guarantee_checks import checks_from_guarantees
from teleguard.agent.load_batch import load_batch_file
from teleguard.agent.minio_client import download_object, list_objects
from teleguard.agent.results_store import AgentRun, append_run, now_utc
from teleguard.agent.seen_state import load_seen, mark_seen
from teleguard.models import BatchContext, Status
from teleguard.onboard.code import (
    DEFAULT_STORE,
    agent_checkpoints,
    confirmed_guarantees,
    list_records,
    load_record,
)
from teleguard.onboard.output_store import MinioOutputStore, parse_output_store

log = logging.getLogger("teleguard.agent")


def process_all_once(
    *,
    store_root: Path = DEFAULT_STORE,
    api_url: str | None = None,
) -> list[AgentRun]:
    """Run one scan across every onboarded pipeline that has an output store."""
    runs: list[AgentRun] = []
    for record in list_records(store_root):
        if not record.output_store:
            continue
        if not agent_checkpoints(record):
            continue
        try:
            runs.extend(
                process_once(
                    record.pipeline_id,
                    store_root=store_root,
                    api_url=api_url,
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.error("pipeline %s: %s", record.pipeline_id, exc)
    return runs


def process_once(
    pipeline_id: str,
    *,
    store_root: Path = DEFAULT_STORE,
    api_url: str | None = None,
) -> list[AgentRun]:
    """Scan confirmed stage folders for new objects and run checks."""
    record = load_record(pipeline_id, store_root=store_root)
    if record is None:
        raise FileNotFoundError(f"no onboard record for {pipeline_id}")
    store = parse_output_store(record.output_store)
    if store is None:
        raise ValueError("output_store not configured; PUT /pipelines/{id}/output-store first")

    guarantees = confirmed_guarantees(record)
    checkpoints = agent_checkpoints(record)
    if not checkpoints:
        log.warning("no confirmed stages with checkpoints; nothing to watch")
        return []

    seen = load_seen(pipeline_id, store_root=store_root)
    runs: list[AgentRun] = []

    for cp in checkpoints:
        stage = cp["stage"]
        checkpoint = cp.get("name") or f"after_{stage}"
        if store.kind == "database":
            runs.extend(
                _process_table(
                    store,
                    pipeline_id=pipeline_id,
                    stage=stage,
                    checkpoint=checkpoint,
                    table=cp.get("object_location") or stage,
                    guarantees=guarantees,
                    seen=seen,
                    store_root=store_root,
                    api_url=api_url,
                )
            )
            continue
        watch = cp.get("object_location") or store.stage_prefix(stage)
        try:
            objects = list_objects(store, watch)
        except Exception as exc:  # noqa: BLE001 - report and continue other stages
            log.error("list_objects failed for stage %s: %s", stage, exc)
            continue

        for obj in objects:
            if obj.key in seen:
                continue
            if not _is_batch_file(obj.key):
                continue
            local: Path | None = None
            try:
                local = download_object(store, obj.key)
                df = load_batch_file(local)
                check_list = checks_from_guarantees(
                    checkpoint,
                    guarantees,
                    columns=df.columns,
                )
                ctx = BatchContext(
                    pipeline=pipeline_id,
                    batch_id=obj.key,
                    segment_column=None,
                )
                results = []
                for check in check_list:
                    results.extend(check.run(df, ctx))
                failed = sum(1 for r in results if r.status is Status.FAIL)
                passed = sum(1 for r in results if r.status is Status.PASS)
                run = AgentRun(
                    pipeline_id=pipeline_id,
                    stage=stage,
                    checkpoint=checkpoint,
                    object_key=obj.key,
                    batch_id=obj.key,
                    observed_at=now_utc(),
                    results=[r.model_dump(mode="json") for r in results],
                    failed=failed,
                    passed=passed,
                )
                if api_url:
                    _post_run(api_url, run)
                else:
                    append_run(run, store_root=store_root)
                mark_seen(pipeline_id, obj.key, store_root=store_root)
                seen.add(obj.key)
                runs.append(run)
                log.info(
                    "processed %s stage=%s fail=%s pass=%s",
                    obj.key,
                    stage,
                    failed,
                    passed,
                )
            except Exception as exc:  # noqa: BLE001
                log.error("failed processing %s: %s", obj.key, exc)
            finally:
                if local is not None and local.exists():
                    local.unlink(missing_ok=True)
    return runs


def _process_table(
    store: MinioOutputStore,
    *,
    pipeline_id: str,
    stage: str,
    checkpoint: str,
    table: str,
    guarantees: list[dict[str, Any]],
    seen: set[str],
    store_root: Path,
    api_url: str | None,
) -> list[AgentRun]:
    """Run checks when the declared table contents change."""
    try:
        frame = read_table(store, table, stage=stage)
    except Exception as exc:  # noqa: BLE001 - one stage must not stop the others
        log.error("read_table failed for stage %s: %s", stage, exc)
        return []
    token = f"db://{table}/{stage}#{table_fingerprint(frame)}"
    if token in seen:
        return []
    ctx = BatchContext(pipeline=pipeline_id, batch_id=token, segment_column=None)
    results = []
    for check in checks_from_guarantees(checkpoint, guarantees, columns=frame.columns):
        results.extend(check.run(frame, ctx))
    failed = sum(1 for item in results if item.status is Status.FAIL)
    passed = sum(1 for item in results if item.status is Status.PASS)
    run = AgentRun(
        pipeline_id=pipeline_id,
        stage=stage,
        checkpoint=checkpoint,
        object_key=token,
        batch_id=token,
        observed_at=now_utc(),
        results=[item.model_dump(mode="json") for item in results],
        failed=failed,
        passed=passed,
    )
    if api_url:
        _post_run(api_url, run)
    else:
        append_run(run, store_root=store_root)
    mark_seen(pipeline_id, token, store_root=store_root)
    seen.add(token)
    return [run]


def run_loop(
    pipeline_id: str | None = None,
    *,
    poll_seconds: float = 5.0,
    store_root: Path = DEFAULT_STORE,
    api_url: str | None = None,
) -> None:
    target = pipeline_id or "(all onboarded with output_store)"
    log.info(
        "agent watching pipeline=%s poll=%ss api=%s",
        target,
        poll_seconds,
        api_url or "(local store only)",
    )
    while True:
        try:
            if pipeline_id:
                process_once(pipeline_id, store_root=store_root, api_url=api_url)
            else:
                process_all_once(store_root=store_root, api_url=api_url)
        except Exception:
            log.exception("agent loop error")
        time.sleep(poll_seconds)


def _is_batch_file(key: str) -> bool:
    lower = key.lower()
    return lower.endswith((".parquet", ".csv", ".json", ".jsonl"))


def _post_run(api_url: str, run: AgentRun) -> None:
    url = api_url.rstrip("/") + f"/pipelines/{run.pipeline_id}/agent/results"
    data = json_bytes(run.to_json())
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"API returned {resp.status}")
    except error.URLError as exc:
        raise RuntimeError(f"POST {url} failed: {exc}") from exc


def json_bytes(payload: dict[str, Any]) -> bytes:
    import json

    return json.dumps(payload).encode("utf-8")
