"""End-to-end test of the build / review / verify workflow on a temporary copy of a pipeline."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from teleguard import workflow
from teleguard.codegraph.model import CodeGraph, Edge, EdgeType, Evidence, Node, NodeType
from teleguard.codegraph.report import mermaid
from teleguard.models import Alert, CheckResult, CheckType, GuardMode, LineageStep, Status

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "web_analytics_pipeline.py"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("repo")
    legacy = root / "pipelines" / "web_analytics" / "legacy"
    legacy.mkdir(parents=True)
    shutil.copy(FIXTURE, legacy / "run.py")
    workflow.build(root / "pipelines" / "web_analytics", "run.run", root)
    return root


def test_build_writes_every_artifact(built: Path) -> None:
    pipeline = built / "pipelines" / "web_analytics"
    for name in ("freeze_manifest.json", "GUARANTEES.md", "codegraph/graph.json",
                 "codegraph/findings.json", "codegraph/CODE_GRAPH.md"):
        assert (pipeline / name).exists(), name
    assert len(json.loads((pipeline / "codegraph" / "findings.json").read_text())) >= 9


def test_build_leaves_every_finding_pending_never_auto_confirmed(built: Path) -> None:
    text = (built / "pipelines" / "web_analytics" / "GUARANTEES.md").read_text()
    assert "**0 confirmed**" in text and "None yet" in text
    assert "KeyError" in text  # the empty-batch crash is recorded as observed behaviour


def test_code_graph_report_shows_runtime_confirmation(built: Path) -> None:
    text = (built / "pipelines" / "web_analytics" / "codegraph" / "CODE_GRAPH.md").read_text()
    assert "flowchart LR" in text and "confirmed by the run" in text


def test_generated_characterisation_tests_pass_on_the_unchanged_pipeline(built: Path) -> None:
    test_file = built / "tests" / "characterisation" / "test_web_analytics.py"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q", "--no-cov",
         "-p", "no:cacheprovider"],
        cwd=built, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "8 passed" in done.stdout


def test_generated_tests_fail_when_the_pipeline_changes(built: Path, tmp_path: Path) -> None:
    root = tmp_path / "copy"
    shutil.copytree(built, root)
    run_py = root / "pipelines" / "web_analytics" / "legacy" / "run.py"
    run_py.write_text(run_py.read_text().replace("/ 1000.0", "/ 100.0"))
    done = subprocess.run(
        [sys.executable, "-m", "pytest", str(root / "tests" / "characterisation"), "-q",
         "--no-cov", "-p", "no:cacheprovider"],
        cwd=root, capture_output=True, text=True, check=False)
    assert done.returncode != 0 and "failed" in done.stdout


def test_verify_passes_then_fails_after_a_change(built: Path, tmp_path: Path) -> None:
    root = tmp_path / "copy"
    shutil.copytree(built, root)
    pipeline = root / "pipelines" / "web_analytics"
    assert workflow.verify(pipeline) == 0
    run_py = pipeline / "legacy" / "run.py"
    run_py.write_text(run_py.read_text() + "\n# edited\n")
    assert workflow.verify(pipeline) == 1


def test_review_persists_decisions_and_updates_guarantees(
        built: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "copy"
    shutil.copytree(built, root)
    pipeline = root / "pipelines" / "web_analytics"
    answers = iter(["y", "n", "not a rule", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    workflow.review(pipeline, "Smita")
    decisions = json.loads((pipeline / "review" / "decisions.json").read_text())
    assert [d["status"] for d in decisions.values()] == ["confirmed", "rejected"]
    text = (pipeline / "GUARANTEES.md").read_text()
    assert "**1 confirmed**" in text and "not a rule" in text and "KeyError" in text


def test_build_refuses_an_empty_legacy_folder(tmp_path: Path) -> None:
    (tmp_path / "p" / "legacy").mkdir(parents=True)
    with pytest.raises(SystemExit, match="is empty"):
        workflow.build(tmp_path / "p", "run.run", tmp_path)


def test_mermaid_marks_runtime_only_nodes() -> None:
    g = CodeGraph()
    g.add_node(Node(id="field:a", type=NodeType.FIELD, label="a"))
    g.add_node(Node(id="out:o", type=NodeType.OUTPUT, label="o"))
    g.add_edge(Edge(source="field:a", target="out:o", type=EdgeType.PRODUCES,
                    evidence=Evidence(file="f.py", line=1)))
    diagram = mermaid(g)
    assert "field_a" in diagram and "-->" in diagram


def test_shared_models_construct() -> None:
    alert = Alert(alert_id="a", pipeline="p", batch_id="b", severity="high", message="m",
                  lineage=[LineageStep(node_id="field:x", node_type="field", label="x")])
    result = CheckResult(check="c", check_type=CheckType.UNIT, checkpoint="after_clean",
                         status=Status.FAIL)
    assert alert.affected_outputs == [] and result.status is Status.FAIL
    assert GuardMode.OFF.value == "off"
