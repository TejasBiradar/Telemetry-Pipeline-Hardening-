"""Tests for the code-graph model, tracer, merge, review, freeze manifest and data generator."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from datagen.generate import GenConfig, generate, write
from teleguard import freeze, guarantees
from teleguard.codegraph.merge import merge
from teleguard.codegraph.model import (
    CodeGraph,
    Edge,
    EdgeType,
    Evidence,
    Node,
    NodeType,
    Origin,
)
from teleguard.findings import Finding, FindingKind
from teleguard.tracer import load_module, trace_pipeline


def _graph() -> CodeGraph:
    """latency_ms -> clean() -> latency_min -> avg_latency; clean() also touches other_in."""
    g = CodeGraph()
    for node in [
        Node(id="field:latency_ms", type=NodeType.FIELD, label="latency_ms"),
        Node(id="field:other_in", type=NodeType.FIELD, label="other_in"),
        Node(id="fn:clean", type=NodeType.FUNCTION, label="clean"),
        Node(id="field:latency_min", type=NodeType.FIELD, label="latency_min"),
        Node(id="field:flag", type=NodeType.FIELD, label="flag"),
        Node(id="out:avg_latency", type=NodeType.OUTPUT, label="avg_latency"),
        Node(id="out:flag_rate", type=NodeType.OUTPUT, label="flag_rate"),
    ]:
        g.add_node(node)
    ev = Evidence(file="c.py", line=3)
    for src, dst, kind in [
        ("field:latency_ms", "fn:clean", EdgeType.READS),
        ("field:other_in", "fn:clean", EdgeType.READS),
        ("fn:clean", "field:latency_min", EdgeType.WRITES),
        ("fn:clean", "field:flag", EdgeType.WRITES),
        ("field:latency_ms", "field:latency_min", EdgeType.DERIVES),
        ("field:other_in", "field:flag", EdgeType.DERIVES),
        ("field:latency_min", "out:avg_latency", EdgeType.PRODUCES),
        ("field:flag", "out:flag_rate", EdgeType.PRODUCES),
    ]:
        g.add_edge(Edge(source=src, target=dst, type=kind, evidence=ev))
    return g


def test_downstream_skips_functions_so_unrelated_outputs_are_not_blamed() -> None:
    affected = {n.label for n in _graph().downstream("field:latency_ms", NodeType.OUTPUT)}
    assert affected == {"avg_latency"}


def test_upstream_returns_only_real_sources() -> None:
    sources = {n.label for n in _graph().upstream("out:avg_latency", NodeType.FIELD)}
    assert sources == {"latency_ms", "latency_min"}


def test_duplicate_nodes_and_edges_are_ignored() -> None:
    g = _graph()
    n_nodes, n_edges = len(g.nodes), len(g.edges)
    g.add_node(Node(id="fn:clean", type=NodeType.FUNCTION, label="again"))
    g.add_edge(g.edges[0])
    assert (len(g.nodes), len(g.edges)) == (n_nodes, n_edges)
    assert g.node("fn:clean").label == "clean"


def test_graph_json_roundtrips_evidence() -> None:
    data = _graph().to_json()
    assert data["edges"][0]["evidence"] == {"file": "c.py", "line": 3, "snippet": ""}


PIPELINE = (
    "import pandas as pd\n"
    "def load(n):\n"
    "    return pd.DataFrame([{'a': i, 'hidden': i * 2} for i in range(n)])\n"
    "def calc(df):\n"
    "    df['b'] = df['a'] + 1\n"
    "    return df[df['a'] > 0]\n"
    "def run(n):\n"
    "    return calc(load(n))\n"
)


def test_tracer_records_columns_and_leaves_module_unwrapped(tmp_path: Path) -> None:
    (tmp_path / "run.py").write_text(PIPELINE)
    module = load_module(tmp_path / "run.py")
    original = module.calc
    trace = trace_pipeline(module, "run", ["load", "calc"], 5)
    assert trace.error is None
    assert [(s.stage, s.rows_out) for s in trace.snapshots] == [("load", 5), ("calc", 4)]
    assert trace.snapshots[1].new_columns == ["b"] and module.calc is original


def test_tracer_reports_a_crash_instead_of_raising(tmp_path: Path) -> None:
    (tmp_path / "run.py").write_text(PIPELINE)
    trace = trace_pipeline(load_module(tmp_path / "run.py"), "run", ["load", "calc"], "x")
    assert trace.error is not None and trace.snapshots == []


def test_merge_marks_origins_and_finds_runtime_only_columns(tmp_path: Path) -> None:
    (tmp_path / "run.py").write_text(PIPELINE)
    from teleguard.adapters.python_pandas import PythonPandasAdapter

    result = PythonPandasAdapter(entry="run.run").analyze(tmp_path)
    labels = [result.graph.node(s).label for s in result.stages]
    trace = trace_pipeline(load_module(tmp_path / "run.py"), "run", labels, 5)
    report = merge(result.graph, trace)
    assert report.runtime_only_fields == ["hidden"]
    assert report.field_agreement == 1.0
    assert result.graph.node("field:hidden").origin is Origin.RUNTIME


def _finding(line: int = 3) -> Finding:
    return Finding(FindingKind.UNIT_CONVERSION, "d_ms", "assumes ms",
                   Evidence(file="c.py", line=line, snippet="x / 1000"))


def test_review_records_decisions_and_skips_already_decided() -> None:
    f1, f2 = _finding(3), _finding(9)
    answers = iter(["y", "n", "wrong, it is data driven"])
    decisions = guarantees.review([f1, f2], {}, "Smita", "2026-10-07", ask=lambda _: next(answers))
    assert decisions[f1.finding_id]["status"] == "confirmed"
    assert decisions[f2.finding_id]["note"] == "wrong, it is data driven"
    again = guarantees.review([f1, f2], decisions, "Other", "later", ask=lambda _: "q")
    assert again == decisions


def test_guarantees_md_only_lists_confirmed_as_guarantees() -> None:
    f1, f2 = _finding(3), _finding(9)
    decisions = {f1.finding_id: {"status": "confirmed", "by": "Smita", "at": "d"}}
    text = guarantees.render("p", [f1, f2], decisions, ["`empty`: crashes"])
    confirmed_part = text.split("## Pending review")[0]
    assert "c.py:3" in confirmed_part and "c.py:9" not in confirmed_part
    assert "1 confirmed" in text and "1 pending" in text and "`empty`: crashes" in text


def test_empty_guarantees_says_none_yet() -> None:
    assert "_None yet._" in guarantees.render("p", [], {}, [])


def test_freeze_detects_change_removal_and_addition(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    manifest = freeze.build_manifest(tmp_path, frozen_at="t")
    assert freeze.verify(tmp_path, manifest) == []
    (tmp_path / "a.py").write_text("x = 2\n")
    (tmp_path / "b.py").unlink()
    (tmp_path / "c.py").write_text("z = 3\n")
    assert sorted(freeze.verify(tmp_path, manifest)) == [
        "added: c.py", "changed: a.py", "missing: b.py"]


def test_datagen_is_seeded_and_realistic(tmp_path: Path) -> None:
    a = write(GenConfig(), tmp_path / "a")
    b = write(GenConfig(), tmp_path / "b")
    assert all(x.read_bytes() == y.read_bytes() for x, y in zip(a, b, strict=True))
    c = write(GenConfig(seed=43), tmp_path / "c")
    assert a[0].read_bytes() != c[0].read_bytes()
    events = [json.loads(line) for line in a[0].read_text().splitlines()]
    assert {"event_id", "timestamp", "user_id", "session_id", "payload"} <= set(events[0])
    assert any(e["user_id"] is None for e in events)


def test_datagen_clean_config_has_no_nulls_or_duplicates() -> None:
    cfg = GenConfig(null_user_rate=0.0, duplicate_rate=0.0, n_batches=1, events_per_batch=100)
    events = generate(cfg)[0]
    assert len(events) == 100 and all(e["user_id"] for e in events)
    assert len({e["event_id"] for e in events}) == 100


@pytest.mark.parametrize("batches", [0, 1])
def test_datagen_handles_tiny_requests(batches: int) -> None:
    out = generate(GenConfig(n_batches=batches, events_per_batch=1, duplicate_rate=0.0))
    assert len(out) == batches
    assert isinstance(pd.DataFrame(out[0] if out else []), pd.DataFrame)
