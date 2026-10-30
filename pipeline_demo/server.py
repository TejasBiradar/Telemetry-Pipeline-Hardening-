"""Pipeline demo: choose a pipeline, trigger a run, write stage files to MinIO."""

from __future__ import annotations

import io
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from minio import Minio
from pydantic import BaseModel

from pipeline_demo.catalog import PipelineSpec, list_pipelines, pipeline_by_id
from pipeline_demo.faults import fault_by_id, list_faults
from pipeline_demo.runner import build_events, frames_from_events, object_key, sample_input
from pipeline_demo.store import store_stage_tables

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Pipeline demo")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_lock = threading.Lock()
_runs: list[dict[str, object]] = []


class RunRequest(BaseModel):
    pipeline: str = "user_behavior"
    fault: str = "clean"


def _client() -> Minio:
    endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    endpoint = endpoint.replace("https://", "").replace("http://", "")
    return Minio(
        endpoint,
        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
    )


def _bucket() -> str:
    return os.environ.get("MINIO_BUCKET", "demo")


def database_url() -> str:
    """Postgres DSN. Compose points this at the postgres service; a host process uses localhost."""
    return os.environ.get(
        "STAGE_DATABASE_URL",
        "postgresql://teleguard:teleguard@localhost:5432/teleguard",
    )


def _storage_label(spec: PipelineSpec) -> str:
    if spec.storage == "single":
        return (
            f"One folder, one file per stage: s3://{_bucket()}/{spec.prefix}/{{stage}}_{{run}}.csv"
        )
    if spec.storage == "database":
        return f"Postgres. One table per stage: {spec.pipeline_id}_{{stage}}. DSN is STAGE_DATABASE_URL."
    return f"One subfolder per stage: s3://{_bucket()}/{spec.prefix}/{{stage}}/{{run}}.csv"


def ensure_bucket() -> None:
    client = _client()
    name = _bucket()
    if not client.bucket_exists(name):
        client.make_bucket(name)


def _upload(frame: pd.DataFrame, key: str) -> None:
    payload = frame.to_csv(index=False).encode("utf-8")
    _client().put_object(
        _bucket(),
        key,
        io.BytesIO(payload),
        length=len(payload),
        content_type="text/csv",
    )


@app.on_event("startup")
def _startup() -> None:
    try:
        ensure_bucket()
    except Exception:  # noqa: BLE001 - MinIO may be unreachable; first trigger retries.
        return


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/pipelines")
def pipelines() -> dict[str, object]:
    return {
        "pipelines": [
            {
                "id": spec.pipeline_id,
                "label": spec.label,
                "stages": list(spec.stages),
                "prefix": spec.prefix,
                "shape": spec.shape,
                "storage": spec.storage,
                "storage_label": _storage_label(spec),
            }
            for spec in list_pipelines()
        ]
    }


@app.get("/faults")
def faults(pipeline: str = Query("user_behavior")) -> dict[str, object]:
    try:
        catalogue = list_faults(pipeline)
        spec = pipeline_by_id(pipeline)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "pipeline": spec.pipeline_id,
        "prefix": spec.prefix,
        "stages": list(spec.stages),
        "faults": [
            {"id": fault.fault_id, "label": fault.label, "detail": fault.detail}
            for fault in catalogue
        ],
    }


@app.get("/sample")
def sample(pipeline: str = Query("user_behavior"), fault: str = Query("clean")) -> dict[str, object]:
    """Rows that Trigger will pass in, after the selected fault."""
    try:
        pipeline_by_id(pipeline)
        fault_by_id(fault, pipeline)
        body = sample_input(pipeline, fault)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    body["pipeline"] = pipeline
    body["fault"] = fault
    return body


@app.get("/runs")
def list_runs(pipeline: str | None = Query(None)) -> dict[str, object]:
    with _lock:
        rows = list(reversed(_runs))
    if pipeline:
        rows = [row for row in rows if row.get("pipeline") == pipeline]
        try:
            prefix = pipeline_by_id(pipeline).prefix
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    else:
        prefix = ""
    return {"bucket": _bucket(), "prefix": prefix, "pipeline": pipeline or "", "runs": rows}


@app.post("/run")
def trigger(body: RunRequest) -> dict[str, object]:
    try:
        spec = pipeline_by_id(body.pipeline)
        fault = fault_by_id(body.fault, body.pipeline)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    record: dict[str, object] = {
        "run_id": run_id,
        "pipeline": spec.pipeline_id,
        "pipeline_label": spec.label,
        "status": "running",
        "fault": fault.fault_id,
        "fault_label": fault.label,
        "prefix": spec.prefix,
        "storage": spec.storage,
        "stages": [],
        "sample": {},
        "error": "",
        "finished_at": "",
    }
    with _lock:
        _runs.append(record)
    try:
        record["sample"] = sample_input(spec.pipeline_id, fault.fault_id)
        if spec.storage == "database":
            frames = frames_from_events(
                build_events(spec.pipeline_id),
                fault=fault.fault_id,
                pipeline_id=spec.pipeline_id,
            )
            written = store_stage_tables(
                database_url(), spec.pipeline_id, frames, spec.stages, run_id
            )
        else:
            ensure_bucket()
            frames = frames_from_events(
                build_events(spec.pipeline_id),
                fault=fault.fault_id,
                pipeline_id=spec.pipeline_id,
            )
            written = []
            for stage in spec.stages:
                key = object_key(spec.prefix, stage, run_id, layout=spec.storage)
                _upload(frames[stage], key)
                written.append(key)
        record["status"] = "succeeded"
        record["stages"] = written
    except Exception as exc:  # noqa: BLE001
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if record["status"] == "failed":
        raise HTTPException(500, str(record["error"]))
    return record
