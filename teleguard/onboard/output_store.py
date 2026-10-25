"""Where a pipeline writes each stage's output.

A stage location is whatever the client declares:

* MinIO folder, ending in ``/`` — every batch file under that prefix
* MinIO object or glob — one file, or a pattern such as ``outputs/ingest_*.csv``
* Database table — rows in that table (connection string stays in the environment)

Credentials are never stored here. The agent reads them from named env vars.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from typing import Any

# Used when a saved store still has only a shared prefix and no per-stage locations.
STAGE_OUTPUT_LAYOUT = "{prefix}/{stage}/"
_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
_COLUMN_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class StageLocation:
    """One confirmed stage and the folder, file, pattern, or table to watch."""

    stage: str
    location: str


@dataclass(frozen=True)
class MinioOutputStore:
    """MinIO or database destination for stage outputs."""

    endpoint: str
    bucket: str
    prefix: str
    secure: bool = True
    # Names of env vars the agent should read (not the secret values).
    access_key_env: str = "MINIO_ACCESS_KEY"
    secret_key_env: str = "MINIO_SECRET_KEY"
    kind: str = "minio"
    dsn_env: str = "STAGE_DATABASE_URL"
    db_layout: str = ""
    stage_column: str = ""
    stages: tuple[StageLocation, ...] = ()

    def normalized_prefix(self) -> str:
        return self.prefix.strip().strip("/")

    def stage_prefix(self, stage: str) -> str:
        """Object-key prefix for one stage (no leading slash, trailing slash)."""
        stage = stage.strip().strip("/")
        if not stage:
            raise ValueError("stage name is empty")
        base = self.normalized_prefix()
        if base:
            return f"{base}/{stage}/"
        return f"{stage}/"

    def stage_uri(self, stage: str) -> str:
        """Logical URI the agent watches for this stage."""
        explicit = self.location_for(stage)
        if explicit:
            return self.describe(explicit)
        return f"s3://{self.bucket}/{self.stage_prefix(stage)}"

    def location_for(self, stage: str) -> str:
        for item in self.stages:
            if item.stage == stage:
                return item.location
        return ""

    def describe(self, location: str) -> str:
        """Human-readable watch target. Secrets are not included."""
        if self.kind == "database":
            return f"db://{location}"
        return f"s3://{self.bucket}/{location.lstrip('/')}"

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.kind,
            "endpoint": self.endpoint,
            "bucket": self.bucket,
            "prefix": self.normalized_prefix(),
            "secure": self.secure,
            "access_key_env": self.access_key_env,
            "secret_key_env": self.secret_key_env,
            "dsn_env": self.dsn_env,
            "db_layout": self.db_layout,
            "stage_column": self.stage_column,
            "stages": [{"stage": item.stage, "location": item.location} for item in self.stages],
        }
        if not self.stages:
            payload["layout"] = STAGE_OUTPUT_LAYOUT
        return payload

    @staticmethod
    def from_json(raw: dict[str, Any]) -> MinioOutputStore:
        kind = str(raw.get("type", "minio"))
        if kind not in {"minio", "database"}:
            raise ValueError(f"unsupported output store type: {kind}")
        endpoint = str(raw.get("endpoint", "")).strip()
        bucket = str(raw.get("bucket", "")).strip()
        prefix = str(raw.get("prefix", "")).strip().strip("/")
        stages = _parse_stages(raw.get("stages", []))
        db_layout = str(raw.get("db_layout", "")).strip()
        stage_column = str(raw.get("stage_column", "")).strip()
        if kind == "minio":
            if not endpoint:
                raise ValueError("output store endpoint is required")
            if not bucket:
                raise ValueError("output store bucket is required")
        else:
            _validate_database(db_layout, stage_column, stages)
        return MinioOutputStore(
            endpoint=endpoint,
            bucket=bucket,
            prefix=prefix,
            secure=bool(raw.get("secure", True)),
            access_key_env=str(raw.get("access_key_env", "MINIO_ACCESS_KEY")),
            secret_key_env=str(raw.get("secret_key_env", "MINIO_SECRET_KEY")),
            kind=kind,
            dsn_env=str(raw.get("dsn_env", "STAGE_DATABASE_URL")).strip() or "STAGE_DATABASE_URL",
            db_layout=db_layout,
            stage_column=stage_column,
            stages=tuple(stages),
        )


def parse_output_store(raw: dict[str, Any] | None) -> MinioOutputStore | None:
    if not raw:
        return None
    return MinioOutputStore.from_json(raw)


def key_matches(key: str, location: str) -> bool:
    """True when an object key is the declared folder, file, or glob."""
    loc = location.strip().lstrip("/")
    if not loc:
        return False
    if any(ch in loc for ch in "*?"):
        return fnmatch.fnmatch(key, loc)
    if loc.endswith("/"):
        return key.startswith(loc) and not key.endswith("/")
    return key == loc


def list_prefix_for(location: str) -> str:
    """MinIO list prefix that can contain matches for ``location``."""
    loc = location.strip().lstrip("/")
    if not loc:
        raise ValueError("location is empty")
    wildcard_at = [loc.find(ch) for ch in "*?" if ch in loc]
    if wildcard_at:
        head = loc[: min(wildcard_at)]
        slash = head.rfind("/")
        return head[: slash + 1] if slash >= 0 else ""
    return loc


def validate_column_name(name: str) -> str:
    """Accept a single SQL identifier. Reject dotted names and anything else."""
    cleaned = name.strip()
    if not _COLUMN_NAME.fullmatch(cleaned):
        raise ValueError(f"column name must be an identifier: {name!r}")
    return cleaned


def validate_table_name(name: str) -> str:
    """Accept ``table`` or ``schema.table``. Reject anything that is not an identifier."""
    cleaned = name.strip()
    if not _TABLE_NAME.fullmatch(cleaned):
        raise ValueError(f"table name must be an identifier: {name!r}")
    return cleaned


def _parse_stages(raw: object) -> list[StageLocation]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError("stages must be a list")
    out: list[StageLocation] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError("each stage location must be an object")
        stage = str(item.get("stage", "")).strip()
        location = str(item.get("location", "")).strip()
        if not stage or not location:
            raise ValueError("stage and location are required")
        if stage in seen:
            raise ValueError(f"duplicate stage location: {stage}")
        seen.add(stage)
        out.append(StageLocation(stage=stage, location=location))
    return out


def _validate_database(layout: str, stage_column: str, stages: list[StageLocation]) -> None:
    if layout not in {"", "per_table", "shared_table"}:
        raise ValueError(f"unsupported database layout: {layout}")
    for item in stages:
        validate_table_name(item.location)
    if layout == "shared_table":
        if not stage_column:
            raise ValueError("stage column is required when every stage shares one table")
        validate_column_name(stage_column)
        tables = {item.location for item in stages}
        if len(tables) != 1:
            raise ValueError("a shared table layout needs the same table for every stage")
