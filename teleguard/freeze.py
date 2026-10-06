"""Freeze manifest: a checksum for every file of the pipeline under test, and a verifier.

Records where the code came from (repository and commit, when known) and what every file
looked like when it was received. `verify` reports any file that was changed, removed or added
since. Nothing here writes into the pipeline itself.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _checksums(legacy: Path) -> dict[str, str]:
    return {
        p.relative_to(legacy).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(legacy.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def build_manifest(legacy: Path, frozen_at: str, repo_url: str | None = None,
                   commit: str | None = None) -> dict[str, Any]:
    return {
        "frozen_at": frozen_at,
        "source": {"repo_url": repo_url, "commit": commit},
        "files": _checksums(legacy),
    }


def verify(legacy: Path, manifest: dict[str, Any]) -> list[str]:
    """Problems found (empty list means the pipeline is exactly as frozen)."""
    expected: dict[str, str] = manifest["files"]
    actual = _checksums(legacy)
    problems = [f"changed: {name}" for name in expected
                if name in actual and actual[name] != expected[name]]
    problems += [f"missing: {name}" for name in expected if name not in actual]
    problems += [f"added: {name}" for name in actual if name not in expected]
    return problems


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
