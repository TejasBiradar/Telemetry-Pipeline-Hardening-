"""Pipeline registry: manage multiple pipelines with dynamic analysis.

Each pipeline can be:
- Built-in (pre-installed, like web_analytics)
- Uploaded (added at runtime)

The registry holds metadata about each pipeline and lazy-loads their graphs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from teleguard.adapters.base import AnalysisResult
from teleguard.contracts.model import Contract


@dataclass
class PipelineMetadata:
    """Metadata for a single pipeline."""

    id: str  # Unique identifier (e.g., "web_analytics" or UUID)
    name: str  # Display name
    description: str = ""
    source_root: Path = field(default_factory=Path)  # Path to pipeline code
    adapter_name: str = "python_pandas"  # "python_pandas" or "sql"
    entry_point: str | None = None  # e.g., "run.run"
    contract: Contract | None = None  # Loaded contract
    analysis: AnalysisResult | None = None  # Cached analysis result
    uploaded_at: datetime = field(default_factory=datetime.now)
    status: str = "ready"  # "ready", "analyzing", "error"
    error_message: str = ""
    # Per-pipeline state
    findings_json: list[dict[str, Any]] = field(default_factory=list)  # Raw findings
    decisions: dict[str, Any] = field(default_factory=dict)  # User decisions on findings

    def graph(self) -> dict[str, Any]:
        """Return graph as JSON, or empty if not analyzed."""
        if self.analysis is None:
            return {"nodes": [], "edges": []}
        return self.analysis.graph.to_json()

    def findings(self) -> list[dict[str, Any]]:
        """Return findings as JSON."""
        return self.findings_json

    def stages(self) -> list[str]:
        """Return ordered stage labels (not internal node ids)."""
        if self.analysis is None:
            return []
        return [self.analysis.graph.node(s).label for s in self.analysis.stages]

    def checkpoints(self) -> list[str]:
        """Return checkpoint names (after each stage + output)."""
        return [f"after_{s}" for s in self.stages()] + ["output"]


@dataclass
class PipelineRegistry:
    """In-memory registry of available pipelines."""

    pipelines: dict[str, PipelineMetadata] = field(default_factory=dict)
    active_pipeline_id: str = ""

    def add(self, pipeline: PipelineMetadata) -> None:
        """Add a pipeline to the registry."""
        self.pipelines[pipeline.id] = pipeline

    def get(self, pipeline_id: str) -> PipelineMetadata | None:
        """Get a pipeline by ID."""
        return self.pipelines.get(pipeline_id)

    def active(self) -> PipelineMetadata | None:
        """Get the currently active pipeline."""
        return self.get(self.active_pipeline_id)

    def select(self, pipeline_id: str) -> bool:
        """Switch to a different pipeline. Returns True if successful."""
        if pipeline_id in self.pipelines:
            self.active_pipeline_id = pipeline_id
            return True
        return False

    def list_all(self) -> list[PipelineMetadata]:
        """List all pipelines."""
        return list(self.pipelines.values())

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON for API response."""
        return {
            "active": self.active_pipeline_id,
            "pipelines": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "adapter": p.adapter_name,
                    "stages": p.stages(),
                    "status": p.status,
                }
                for p in self.list_all()
            ],
        }
