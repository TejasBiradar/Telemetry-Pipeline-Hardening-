"""Pipeline demo: one trigger, run status, stage files written to MinIO."""

from __future__ import annotations

import io
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from minio import Minio
from pydantic import BaseModel

from pipeline_demo.faults import fault_by_id, list_faults
from pipeline_demo.runner import STAGES, build_events, frames_from_events, object_key

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Pipeline demo")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_lock = threading.Lock()
_runs: list[dict[str, object]] = []


class RunRequest(BaseModel):
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


def _prefix() -> str:
    return os.environ.get("MINIO_PREFIX", "demo/user_behavior/outputs")


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
    except (OSError, RuntimeError):
        # MinIO may still be starting; the first trigger retries.
        return


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/faults")
def faults() -> dict[str, object]:
    return {
        "faults": [
            {"id": fault.fault_id, "label": fault.label, "detail": fault.detail}
            for fault in list_faults()
        ]
    }


@app.get("/runs")
def list_runs() -> dict[str, object]:
    with _lock:
        rows = list(reversed(_runs))
    return {"prefix": _prefix(), "bucket": _bucket(), "runs": rows}


@app.post("/run")
def trigger(body: RunRequest) -> dict[str, object]:
    try:
        fault = fault_by_id(body.fault)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    record: dict[str, object] = {
        "run_id": run_id,
        "status": "running",
        "fault": fault.fault_id,
        "fault_label": fault.label,
        "stages": [],
        "error": "",
        "finished_at": "",
    }
    with _lock:
        _runs.append(record)
    try:
        ensure_bucket()
        frames = frames_from_events(build_events(), fault=fault.fault_id)
        written: list[str] = []
        for stage in STAGES:
            key = object_key(_prefix(), stage, run_id)
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
