"""Adapter tests on toy pipelines deliberately unlike any real one, so they prove genericity."""

from __future__ import annotations

from pathlib import Path

import pytest

from teleguard.adapters.base import AnalysisResult
from teleguard.adapters.python_pandas import PythonPandasAdapter, field_id, output_id
from teleguard.adapters.sql import SQLAdapter
from teleguard.codegraph.model import EdgeType, NodeType
from teleguard.findings import FindingKind

TOY = {
    "settings.py": (
        'LOOKUP = {"a": "A", "b": "NA"}\n'
        "LIMIT = 500\n"
        'WORD = "fail"\n'
        'KEYS = ["day", "site"]\n'
    ),
    "stage_one.py": (
        "import pandas as pd\n\n"
        "def load(rows):\n"
        "    df = pd.DataFrame(rows)\n"
        '    df["when"] = pd.to_datetime(df["epoch"], unit="s", utc=True)\n'
        "    return df\n"
    ),
    "stage_two.py": (
        "from .settings import LOOKUP, LIMIT, WORD\n\n"
        "def tidy(df):\n"
        '    df = df.drop_duplicates(subset="rid")\n'
        '    df = df[df["sensor"].notna()].copy()\n'
        '    df["temp_c"] = df["temp_f_x10"] * 0.1\n'
        '    df = df[df["temp_c"] < LIMIT]\n'
        '    df["site"] = df["code"].map(LOOKUP).fillna("?")\n'
        '    df["failed"] = df["note"].str.contains(WORD, na=False)\n'
        '    df["tag_prefix"] = df["tag"].str.split("-").str[0]\n'
        '    df["day"] = df["when"].dt.date\n'
        "    return df\n"
    ),
    "summary.py": (
        "from .settings import KEYS\n\n"
        "def summarise(df):\n"
        '    return df.groupby(KEYS).agg(avg_temp=("temp_c", "mean"), fails=("failed", "sum"))\n'
    ),
    "main.py": (
        "from .stage_one import load\n"
        "from .stage_two import tidy\n"
        "from .summary import summarise\n\n"
        "def main(rows):\n"
        "    df = load(rows)\n"
        "    df = tidy(df)\n"
        "    return summarise(df)\n"
    ),
}


@pytest.fixture(scope="module")
def toy(tmp_path_factory: pytest.TempPathFactory) -> AnalysisResult:
    root = tmp_path_factory.mktemp("toy")
    for name, body in TOY.items():
        (root / name).write_text(body)
    return PythonPandasAdapter(entry="main.main").analyze(root)


def _kinds(result: AnalysisResult, field: str) -> set[FindingKind]:
    return {f.kind for f in result.findings if f.field == field}


def test_stages_and_checkpoints_follow_call_order(toy: AnalysisResult) -> None:
    assert [toy.graph.node(s).label for s in toy.stages] == ["load", "tidy", "summarise"]
    assert [c.name for c in toy.checkpoints] == ["after_load", "after_tidy", "after_summarise"]
    assert toy.checkpoints[1].location == "main.py:7"


def test_lineage_follows_data_not_functions(toy: AnalysisResult) -> None:
    affected = {n.id for n in toy.graph.downstream(field_id("temp_f_x10"), NodeType.OUTPUT)}
    assert affected == {output_id("avg_temp")}
    sources = {n.label for n in toy.graph.upstream(output_id("fails"), NodeType.FIELD)}
    assert sources == {"failed", "note"}


def test_derivation_keeps_formula_and_evidence(toy: AnalysisResult) -> None:
    edge = next(e for e in toy.graph.edges
                if e.type is EdgeType.DERIVES and e.target == field_id("temp_c"))
    assert edge.attrs["formula"] == "df['temp_f_x10'] * 0.1"
    assert edge.evidence is not None and edge.evidence.file == "stage_two.py"


@pytest.mark.parametrize(("field", "kind"), [
    ("temp_f_x10", FindingKind.UNIT_CONVERSION), ("epoch", FindingKind.TIMESTAMP_UNIT),
    ("epoch", FindingKind.TIMEZONE), ("rid", FindingKind.DEDUP_KEY),
    ("sensor", FindingKind.REQUIRED_FIELD), ("temp_c", FindingKind.ROW_FILTER),
    ("code", FindingKind.UNMAPPED_TO_NULL), ("code", FindingKind.DEFAULT_FILL),
    ("code", FindingKind.NULL_LOOKALIKE_VALUE), ("note", FindingKind.KEYWORD_MATCH),
    ("tag", FindingKind.STRING_FORMAT), ("day", FindingKind.GROUP_KEY_DROPS_NULLS),
    ("tag_prefix", FindingKind.UNUSED_FIELD),
])
def test_detects_hidden_rule(toy: AnalysisResult, field: str, kind: FindingKind) -> None:
    assert kind in _kinds(toy, field)


def test_findings_carry_line_evidence(toy: AnalysisResult) -> None:
    unit = next(f for f in toy.findings if f.kind is FindingKind.UNIT_CONVERSION)
    assert (unit.evidence.file, unit.evidence.line) == ("stage_two.py", 6)


def test_notna_filter_is_reported_once_as_required(toy: AnalysisResult) -> None:
    assert _kinds(toy, "sensor") == {FindingKind.REQUIRED_FIELD}


def test_function_local_lookup_table_is_resolved(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(
        'def f(df):\n    table = {"x": "NA"}\n    df["r"] = df["c"].map(table)\n    return df\n')
    kinds = {f.kind for f in PythonPandasAdapter().analyze(tmp_path).findings}
    assert {FindingKind.UNMAPPED_TO_NULL, FindingKind.NULL_LOOKALIKE_VALUE} <= kinds


def test_groupby_dropna_false_is_not_flagged(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        'def f(df):\n    return df.groupby("k", dropna=False).agg(n=("v", "count"))\n')
    kinds = {f.kind for f in PythonPandasAdapter().analyze(tmp_path).findings}
    assert FindingKind.GROUP_KEY_DROPS_NULLS not in kinds


def test_empty_directory_gives_empty_graph(tmp_path: Path) -> None:
    result = PythonPandasAdapter(entry=None).analyze(tmp_path)
    assert result.graph.nodes == [] and result.findings == []


SQL = """-- stage one
CREATE TEMP TABLE cleaned AS
SELECT user_id, amount_cents / 100.0 AS amount_usd,
       SPLIT_PART(client_version, '.', 1) AS major, COALESCE(country, 'Other') AS country
FROM raw
WHERE user_id IS NOT NULL AND amount_cents > 0 AND note ILIKE '%error%';

CREATE TABLE daily AS
SELECT country, COUNT(*) AS n, AVG(amount_usd) AS avg_usd FROM cleaned GROUP BY country;
"""


@pytest.fixture(scope="module")
def sql(tmp_path_factory: pytest.TempPathFactory) -> AnalysisResult:
    root = tmp_path_factory.mktemp("sql")
    (root / "p.sql").write_text(SQL)
    return SQLAdapter().analyze(root)


@pytest.mark.parametrize(("field", "kind"), [
    ("amount_cents", FindingKind.UNIT_CONVERSION), ("client_version", FindingKind.STRING_FORMAT),
    ("country", FindingKind.DEFAULT_FILL), ("user_id", FindingKind.REQUIRED_FIELD),
    ("amount_cents", FindingKind.ROW_FILTER), ("note", FindingKind.KEYWORD_MATCH),
])
def test_sql_detects_hidden_rule(sql: AnalysisResult, field: str, kind: FindingKind) -> None:
    assert kind in _kinds(sql, field)


def test_sql_stages_and_lineage(sql: AnalysisResult) -> None:
    assert [sql.graph.node(s).label for s in sql.stages] == ["cleaned", "daily"]
    affected = {n.label for n in sql.graph.downstream(field_id("amount_cents"), NodeType.OUTPUT)}
    assert affected == {"avg_usd"}


def test_not_null_test_is_recognised_in_both_sqlglot_shapes() -> None:
    from sqlglot import exp

    from teleguard.adapters.sql import not_null_column

    column = exp.column("user_id")
    old_shape = exp.Not(this=exp.Is(this=column.copy(), expression=exp.Null()))
    new_shape = exp.Is(this=column.copy(), expression=exp.Null(), negate=True)
    plain_is_null = exp.Is(this=column.copy(), expression=exp.Null())
    assert not_null_column(old_shape) == "user_id"
    assert not_null_column(new_shape) == "user_id"
    assert not_null_column(plain_is_null) is None


def test_sql_group_by_does_not_claim_null_dropping(sql: AnalysisResult) -> None:
    assert FindingKind.GROUP_KEY_DROPS_NULLS not in {f.kind for f in sql.findings}


def test_sql_line_numbers_point_at_the_statement(sql: AnalysisResult) -> None:
    unit = next(f for f in sql.findings if f.kind is FindingKind.UNIT_CONVERSION)
    assert unit.evidence.line == 2


def test_sql_directory_without_sql_is_empty(tmp_path: Path) -> None:
    assert SQLAdapter().analyze(tmp_path).graph.nodes == []
