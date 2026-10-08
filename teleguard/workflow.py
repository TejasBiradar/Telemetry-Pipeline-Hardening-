"""Understand-and-protect workflow for one pipeline.

    python -m teleguard.workflow build  pipelines/web_analytics --entry run.run
    python -m teleguard.workflow review pipelines/web_analytics --reviewer "Name"
    python -m teleguard.workflow verify pipelines/web_analytics

`build` freezes a checksum manifest, builds the code graph (static analysis plus one
confirmation run), drafts GUARANTEES.md with every finding pending, and writes the
characterisation tests. `review` records a person's decision on each finding and regenerates
GUARANTEES.md. `verify` checks the pipeline still matches its freeze manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from datagen.generate import GenConfig, write
from teleguard import characterisation, freeze, guarantees
from teleguard.adapters.base import AnalysisResult
from teleguard.analyze import analyze_legacy
from teleguard.codegraph.merge import MergeReport, merge
from teleguard.codegraph.report import report_markdown
from teleguard.findings import Finding
from teleguard.pipeline_loader import source_root_for
from teleguard.tracer import load_module, trace_pipeline


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _confirm_by_running(legacy: Path, entry: str, result: AnalysisResult) -> MergeReport | None:
    module_name, func = entry.rsplit(".", 1)
    path = legacy / f"{module_name}.py"
    if not path.exists():
        return None
    stages = [result.graph.node(s).label for s in result.stages]
    with tempfile.TemporaryDirectory() as tmp:
        write(GenConfig(), Path(tmp))
        trace = trace_pipeline(load_module(path), func, stages, Path(tmp))
    if trace.error:
        print(f"  runtime confirmation stopped early: {trace.error}")
    return merge(result.graph, trace)


def _findings_from_json(path: Path) -> list[Finding]:
    from teleguard.codegraph.model import Evidence
    from teleguard.findings import FindingKind

    return [Finding(FindingKind(d["kind"]), d["field"], d["message"], Evidence(**d["evidence"]))
            for d in json.loads(path.read_text())]


def build(pipeline_dir: Path, entry: str, repo_root: Path) -> None:
    legacy = source_root_for(pipeline_dir)
    if not legacy.is_dir() or not any(legacy.iterdir()):
        raise SystemExit(f"{legacy} is empty: copy the pipeline in first (agents cannot write "
                         "into legacy/, by design; demo pipelines may use source_dir: src)")
    print("1/4 Freeze manifest")
    manifest = freeze.build_manifest(legacy, frozen_at=_now())
    freeze.write_manifest(pipeline_dir / "freeze_manifest.json", manifest)
    print(f"    {len(manifest['files'])} files fingerprinted")

    print("2/4 Code graph")
    try:
        result, language = analyze_legacy(legacy, entry=entry)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    merged = _confirm_by_running(legacy, entry, result) if language == "python" else None
    out = pipeline_dir / "codegraph"
    out.mkdir(exist_ok=True)
    (out / "graph.json").write_text(json.dumps(result.graph.to_json(), indent=2))
    (out / "findings.json").write_text(json.dumps([f.to_json() for f in result.findings],
                                                  indent=2))
    (out / "CODE_GRAPH.md").write_text(report_markdown(pipeline_dir.name, result, merged))
    print(f"    {len(result.graph.nodes)} nodes, {len(result.graph.edges)} edges, "
          f"{len(result.findings)} findings")
    if merged:
        print(f"    runtime agreement: {merged.field_agreement:.0%} of fields, "
              f"{merged.edge_agreement:.0%} of links; "
              f"{len(merged.runtime_only_fields)} columns seen only at runtime")

    observed: list[str] = []
    if language == "python":
        print("3/4 Characterisation tests")
        outcomes = characterisation.build(pipeline_dir, repo_root)
        observed = [o.describe() for o in outcomes]
        for line in observed:
            print(f"    {line}")
    else:
        print("3/4 Characterisation tests: skipped (needs a runnable Python pipeline)")

    print("4/4 GUARANTEES.md draft")
    decisions = guarantees.load_decisions(pipeline_dir / "review" / "decisions.json")
    (pipeline_dir / "GUARANTEES.md").write_text(
        guarantees.render(pipeline_dir.name, result.findings, decisions, observed))
    undecided = sum(1 for f in result.findings if f.finding_id not in decisions)
    print(f"    {undecided} findings waiting for review: run the `review` command")


def review(pipeline_dir: Path, reviewer: str) -> None:
    findings = _findings_from_json(pipeline_dir / "codegraph" / "findings.json")
    path = pipeline_dir / "review" / "decisions.json"
    decisions = guarantees.review(findings, guarantees.load_decisions(path), reviewer, _now(),
                                  ask=input)
    guarantees.save_decisions(path, decisions)
    observed_file = pipeline_dir / "GUARANTEES.md"
    previous = observed_file.read_text() if observed_file.exists() else ""
    marker = "## Observed behaviour on unusual input"
    observed = [ln[2:] for ln in previous.split(marker)[-1].splitlines() if ln.startswith("- ")]
    observed_file.write_text(guarantees.render(pipeline_dir.name, findings, decisions, observed))
    confirmed = sum(1 for d in decisions.values() if d["status"] == "confirmed")
    print(f"\nSaved. {confirmed} confirmed, {len(decisions)} decided of {len(findings)}.")


def verify(pipeline_dir: Path) -> int:
    manifest = json.loads((pipeline_dir / "freeze_manifest.json").read_text())
    problems = freeze.verify(source_root_for(pipeline_dir), manifest)
    for p in problems:
        print(f"  {p}")
    print("OK: pipeline matches its freeze manifest" if not problems
          else f"FAILED: {len(problems)} difference(s) from the freeze manifest")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="teleguard.workflow")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "review", "verify"):
        cmd = sub.add_parser(name)
        cmd.add_argument("pipeline_dir", type=Path)
        if name == "build":
            cmd.add_argument("--entry", default="run.run", help="module.function, e.g. run.run")
        if name == "review":
            cmd.add_argument("--reviewer", required=True)
    args = parser.parse_args(argv)
    if args.command == "build":
        build(args.pipeline_dir, args.entry, Path.cwd())
    elif args.command == "review":
        review(args.pipeline_dir, args.reviewer)
    else:
        return verify(args.pipeline_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
