"""Thin MinIO helper for the watcher agent."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from teleguard.onboard.output_store import MinioOutputStore, key_matches, list_prefix_for


@dataclass(frozen=True)
class MinioObject:
    key: str
    etag: str
    size: int


def connect(store: MinioOutputStore):  # type: ignore[no-untyped-def]
    """Return a ``minio.Minio`` client using env credentials named in ``store``."""
    from minio import Minio

    access = os.environ.get(store.access_key_env, "")
    secret = os.environ.get(store.secret_key_env, "")
    if not access or not secret:
        raise RuntimeError(
            f"set {store.access_key_env} and {store.secret_key_env} for MinIO access"
        )
    endpoint = store.endpoint.replace("https://", "").replace("http://", "")
    return Minio(
        endpoint,
        access_key=access,
        secret_key=secret,
        secure=store.secure,
    )


def list_objects(store: MinioOutputStore, location: str) -> list[MinioObject]:
    """List objects for a folder, an exact key, or a glob such as ``outputs/ingest_*.csv``."""
    client = connect(store)
    prefix = list_prefix_for(location)
    out: list[MinioObject] = []
    for obj in client.list_objects(store.bucket, prefix=prefix, recursive=True):
        if obj.is_dir:
            continue
        key = str(obj.object_name or "")
        if not key or key.endswith("/") or not key_matches(key, location):
            continue
        out.append(
            MinioObject(
                key=key,
                etag=str(obj.etag or ""),
                size=int(obj.size or 0),
            )
        )
    return out


def download_object(store: MinioOutputStore, key: str) -> Path:
    """Download object to a temp file; caller should delete when done."""
    client = connect(store)
    suffix = Path(key).suffix or ".bin"
    fd, name = tempfile.mkstemp(prefix="teleguard-obj-", suffix=suffix)
    os.close(fd)
    path = Path(name)
    client.fget_object(store.bucket, key, str(path))
    return path
