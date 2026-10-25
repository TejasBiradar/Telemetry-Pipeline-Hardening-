"""Persist agent check runs for the API (metadata only, not raw dumps)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from teleguard.onboard.code import DEFAULT_STORE


def _runs_path(pipeline_id: str, store_root: Path = DEFAULT_STORE) -> Path:
    return store_root / pipeline_id / "agent_runs.jsonl"


@dataclass(frozen=True)
class AgentRun:
    pipeline_id: str
    stage: str
    checkpoint: str
    object_key: str
    batch_id: str
    observed_at: str
    results: list[dict[str, Any]]
    failed: int
    passed: int

    def to_json(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "stage": self.stage,
            "checkpoint": self.checkpoint,
            "object_key": self.object_key,
            "batch_id": self.batch_id,
            "observed_at": self.observed_at,
            "results": self.results,
            "failed": self.failed,
            "passed": self.passed,
        }

    @staticmethod
    def from_json(raw: dict[str, Any]) -> AgentRun:
        return AgentRun(
            pipeline_id=str(raw["pipeline_id"]),
            stage=str(raw["stage"]),
            checkpoint=str(raw["checkpoint"]),
            object_key=str(raw["object_key"]),
            batch_id=str(raw["batch_id"]),
            observed_at=str(raw["observed_at"]),
            results=list(raw.get("results", [])),
            failed=int(raw.get("failed", 0)),
            passed=int(raw.get("passed", 0)),
        )


def append_run(run: AgentRun, store_root: Path = DEFAULT_STORE) -> None:
    path = _runs_path(run.pipeline_id, store_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run.to_json()) + "\n")


def list_runs(
    pipeline_id: str,
    *,
    limit: int = 50,
    store_root: Path = DEFAULT_STORE,
) -> list[AgentRun]:
    path = _runs_path(pipeline_id, store_root)
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    runs: list[AgentRun] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        raw: object = json.loads(line)
        if isinstance(raw, dict):
            runs.append(AgentRun.from_json(raw))
    return runs


def latest_run(pipeline_id: str, store_root: Path = DEFAULT_STORE) -> AgentRun | None:
    all_runs = list_runs(pipeline_id, limit=10_000, store_root=store_root)
    return all_runs[-1] if all_runs else None


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
