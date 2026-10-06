"""Adapter interface. One adapter per pipeline style; the rest of the system never changes.

Shared contract (CLAUDE.md rule 7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from teleguard.codegraph.model import CodeGraph
from teleguard.findings import Finding


class AttachMode(str, Enum):
    IN_PROCESS_HOOK = "in_process_hook"
    OUT_OF_PROCESS_TAP = "out_of_process_tap"


@dataclass(frozen=True)
class Checkpoint:
    name: str
    after_stage: str
    attach: AttachMode
    location: str


@dataclass
class AnalysisResult:
    graph: CodeGraph
    findings: list[Finding] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    checkpoints: list[Checkpoint] = field(default_factory=list)


class Adapter(Protocol):
    name: str

    def source_files(self, root: Path) -> list[Path]: ...

    def analyze(self, root: Path) -> AnalysisResult: ...
