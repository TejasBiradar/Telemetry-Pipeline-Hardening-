"""Renders an `EvaluationReport` as the evidence the panel asks for: a detection matrix
and a precision/recall/lag table, per system, side by side."""

from __future__ import annotations

import json
from pathlib import Path

from teleguard.evaluate.engine import EvaluationReport


def render_markdown(reports: list[EvaluationReport]) -> str:
    lines = ["# Evaluation report", "", "## Summary", "",
            "| System | Precision | Recall | Mean lag (batches) |",
            "|---|---|---|---|"]
    for r in reports:
        lag = f"{r.mean_lag_batches:.1f}" if r.mean_lag_batches is not None else "-"
        lines.append(f"| {r.system_name} | {r.precision:.2f} | {r.recall:.2f} | {lag} |")

    lines += ["", "## Detection matrix", "",
             "| Scenario | " + " | ".join(r.system_name for r in reports) + " |",
             "|---|" + "---|" * len(reports)]
    scenario_names = [s.scenario_name for s in reports[0].scores] if reports else []
    for name in scenario_names:
        cells = []
        for r in reports:
            matching = next((s for s in r.scores if s.scenario_name == name), None)
            cells.append("caught" if matching and matching.detected else "missed")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    return "\n".join(lines) + "\n"


def render_json(reports: list[EvaluationReport]) -> dict[str, object]:
    return {"systems": [r.to_json() for r in reports]}


def write_report(reports: list[EvaluationReport], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evaluation_report.md").write_text(render_markdown(reports))
    (out_dir / "evaluation_report.json").write_text(json.dumps(render_json(reports), indent=2))
