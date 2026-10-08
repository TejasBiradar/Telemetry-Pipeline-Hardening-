"""Demo onboard record: alert email + which pipeline it belongs to."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "demo_onboard.json"


@dataclass
class OnboardRecord:
    email: str
    pipeline_id: str
    source_note: str = ""


def load_onboard(path: Path = DEFAULT_PATH) -> OnboardRecord | None:
    if not path.exists():
        return None
    raw: object = json.loads(path.read_text())
    if not isinstance(raw, dict):
        return None
    email = str(raw.get("email", "")).strip()
    pipeline_id = str(raw.get("pipeline_id", "")).strip()
    if not email or not pipeline_id:
        return None
    return OnboardRecord(
        email=email,
        pipeline_id=pipeline_id,
        source_note=str(raw.get("source_note", "")),
    )


def save_onboard(record: OnboardRecord, path: Path = DEFAULT_PATH) -> None:
    if not _EMAIL.match(record.email):
        raise ValueError("invalid email address")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "email": record.email,
                "pipeline_id": record.pipeline_id,
                "source_note": record.source_note,
            },
            indent=2,
        )
        + "\n"
    )
