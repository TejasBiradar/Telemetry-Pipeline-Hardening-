"""SQL adapter: static analysis of a SQL pipeline into the common code graph.

Each statement (CREATE TABLE ... AS SELECT, or a bare SELECT) is one stage. Columns are
`field:<name>` nodes, as in the pandas adapter, so lineage works the same way. The last
statement's columns are the pipeline outputs.

Only rules that are true for SQL are reported. For example GROUP BY keeps NULL keys as their
own group (unlike pandas), so no "drops nulls" finding is produced.
"""

from __future__ import annotations

from pathlib import Path

import sqlglot
from sqlglot import exp

from teleguard.adapters.base import AnalysisResult, AttachMode, Checkpoint
from teleguard.codegraph.model import CodeGraph, Edge, EdgeType, Evidence, Node, NodeType
from teleguard.findings import Finding, FindingKind


def _split_statements(source: str) -> list[tuple[int, str]]:
    """(first line number, text) per ';'-terminated statement, ignoring comment-only lines."""
    statements: list[tuple[int, str]] = []
    current: list[str] = []
    start = 0
    for number, line in enumerate(source.splitlines(), start=1):
        if not current and (not line.strip() or line.strip().startswith("--")):
            continue
        if not current:
            start = number
        current.append(line)
        if line.rstrip().endswith(";"):
            statements.append((start, "\n".join(current)))
            current = []
    if current:
        statements.append((start, "\n".join(current)))
    return statements


class SQLAdapter:
    name = "sql"

    def source_files(self, root: Path) -> list[Path]:
        return sorted(root.rglob("*.sql"))

    def analyze(self, root: Path) -> AnalysisResult:
        graph = CodeGraph()
        findings: list[Finding] = []
        parsed: list[tuple[str, int, str, exp.Select]] = []

        for path in self.source_files(root):
            rel = path.relative_to(root).as_posix()
            for line_no, text in _split_statements(path.read_text()):
                select, table = self._select_and_table(sqlglot.parse_one(text, read="postgres"))
                if select is not None:
                    parsed.append((rel, line_no, table, select))

        stage_ids: list[str] = []
        for index, (rel, line_no, table, select) in enumerate(parsed):
            is_last = index == len(parsed) - 1
            stage_id = f"stage:{index + 1}:{table}"
            fn_id = f"fn:{table}"
            graph.add_node(Node(id=stage_id, type=NodeType.STAGE, label=table, attrs={
                "order": index + 1, "function": fn_id, "called_at": f"{rel}:{line_no}"}))
            graph.add_node(Node(id=fn_id, type=NodeType.FUNCTION, label=table,
                                attrs={"file": rel, "line": line_no}))
            graph.add_edge(Edge(source=stage_id, target=fn_id, type=EdgeType.CALLS))
            if stage_ids:
                graph.add_edge(Edge(source=stage_ids[-1], target=stage_id,
                                    type=EdgeType.NEXT_STAGE))
            stage_ids.append(stage_id)
            findings.extend(self._analyze_select(graph, select, fn_id, rel, line_no, is_last))

        checkpoints = [
            Checkpoint(name=f"after_{graph.node(s).label}", after_stage=s,
                       attach=AttachMode.OUT_OF_PROCESS_TAP,
                       location=str(graph.node(s).attrs["called_at"]))
            for s in stage_ids
        ]
        return AnalysisResult(graph=graph, findings=findings, stages=stage_ids,
                              checkpoints=checkpoints)

    @staticmethod
    def _select_and_table(stmt: exp.Expr) -> tuple[exp.Select | None, str]:
        if isinstance(stmt, exp.Create) and isinstance(stmt.expression, exp.Select):
            this = stmt.this
            table = this.find(exp.Table)
            return stmt.expression, (table.name if table else "result")
        if isinstance(stmt, exp.Select):
            return stmt, "result"
        return None, ""

    def _analyze_select(self, graph: CodeGraph, select: exp.Select, fn_id: str, rel: str,
                        line_no: int, is_last: bool) -> list[Finding]:
        findings: list[Finding] = []
        evidence = Evidence(file=rel, line=line_no, snippet=select.sql(dialect="postgres")[:200])

        def field(name: str) -> str:
            node_id = f"field:{name}"
            if not graph.has_node(node_id):
                graph.add_node(Node(id=node_id, type=NodeType.FIELD, label=name))
            return node_id

        def output(name: str) -> str:
            node_id = f"out:{name}"
            if not graph.has_node(node_id):
                graph.add_node(Node(id=node_id, type=NodeType.OUTPUT, label=name))
            return node_id

        for projection in select.expressions:
            target = projection.alias_or_name
            expr = projection.this if isinstance(projection, exp.Alias) else projection
            sources = sorted({c.name for c in expr.find_all(exp.Column)})
            formula = expr.sql(dialect="postgres")
            for src in sources:
                graph.add_edge(Edge(source=field(src), target=fn_id, type=EdgeType.READS,
                                    evidence=evidence))
            graph.add_edge(Edge(source=fn_id, target=field(target), type=EdgeType.WRITES,
                                evidence=evidence))
            for src in sources:
                if src != target or not isinstance(expr, exp.Column):
                    graph.add_edge(Edge(source=field(src), target=field(target),
                                        type=EdgeType.DERIVES, evidence=evidence,
                                        attrs={"formula": formula}))
                if is_last:
                    graph.add_edge(Edge(source=field(src), target=output(target),
                                        type=EdgeType.PRODUCES, evidence=evidence,
                                        attrs={"how": formula}))
            findings.extend(self._expression_findings(expr, target, rel, line_no))

        where = select.args.get("where")
        if where is not None:
            findings.extend(self._where_findings(where, rel, line_no))
        return findings

    @staticmethod
    def _expression_findings(expr: exp.Expression, target: str, rel: str,
                             line: int) -> list[Finding]:
        found: list[Finding] = []

        def add(kind: FindingKind, col: str | None, message: str, node: exp.Expr) -> None:
            found.append(Finding(kind, col, message, Evidence(
                file=rel, line=line, snippet=node.sql(dialect="postgres")[:200])))

        for arith in expr.find_all(exp.Div, exp.Mul):
            arith_cols = list(arith.find_all(exp.Column))
            literals = [n for n in (arith.left, arith.right) if isinstance(n, exp.Literal)
                        and not n.is_string]
            if len(arith_cols) == 1 and literals and float(literals[0].this) not in (0.0, 1.0):
                add(FindingKind.UNIT_CONVERSION, arith_cols[0].name,
                    f"'{target}' = {arith.sql(dialect='postgres')}: assumes "
                    f"'{arith_cols[0].name}' is in the unit that this factor "
                    f"({literals[0].this}) converts from", arith)
        for fill in expr.find_all(exp.Coalesce):
            fill_col = fill.this.name if isinstance(fill.this, exp.Column) else None
            add(FindingKind.DEFAULT_FILL, fill_col,
                f"missing values are silently replaced with "
                f"{', '.join(e.sql() for e in fill.expressions)}", fill)
        for case in expr.find_all(exp.Case):
            default = case.args.get("default")
            case_cols = sorted({c.name for c in case.find_all(exp.Column)})
            if default is not None:
                add(FindingKind.DEFAULT_FILL, case_cols[0] if case_cols else None,
                    f"values matching none of the CASE branches silently become "
                    f"{default.sql()}", case)
        for text in expr.find_all(exp.Split, exp.SplitPart, exp.Substring):
            text_col = next((c.name for c in text.find_all(exp.Column)), None)
            add(FindingKind.STRING_FORMAT, text_col,
                f"'{text_col}' is assumed to have a fixed text format: "
                f"{text.sql(dialect='postgres')}", text)
        return found

    @staticmethod
    def _where_findings(where: exp.Where, rel: str, line: int) -> list[Finding]:
        found: list[Finding] = []
        conditions = list(where.this.flatten()) if isinstance(where.this, exp.And) \
            else [where.this]
        for cond in conditions:
            snippet = cond.sql(dialect="postgres")
            evidence = Evidence(file=rel, line=line, snippet=snippet[:200])
            columns = [c.name for c in cond.find_all(exp.Column)]
            if not columns:
                continue
            if isinstance(cond, exp.Not) and isinstance(cond.this, exp.Is) \
                    and isinstance(cond.this.expression, exp.Null):
                found.append(Finding(FindingKind.REQUIRED_FIELD, columns[0],
                                     f"rows with missing '{columns[0]}' are removed: "
                                     f"'{columns[0]}' is treated as required", evidence))
            elif isinstance(cond, (exp.Like, exp.ILike)):
                found.append(Finding(FindingKind.KEYWORD_MATCH, columns[0],
                                     f"'{columns[0]}' is matched against the text pattern "
                                     f"in `{snippet}`: wording changes break it", evidence))
            else:
                found.append(Finding(FindingKind.ROW_FILTER, columns[0],
                                     f"keeps only rows where {snippet}; other rows are "
                                     "dropped silently", evidence))
        return found
