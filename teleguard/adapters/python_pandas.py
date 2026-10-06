"""Python/pandas adapter: static analysis of a pandas pipeline into the common code graph.

Nothing is executed. It extracts functions, calls, DataFrame columns read/written/derived
(with formulas), named aggregations as outputs, the stage order from an entry function, and
*findings*: code patterns that imply a hidden rule (unit conversions, silent row filters,
group keys that drop nulls, keyword matching, ...).

Limits (the runtime tracer covers them): column names built at runtime, columns created from
records or json_normalize, and names that are not literals or literal constants.
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path
from typing import Any

from teleguard.adapters.base import AnalysisResult, AttachMode, Checkpoint
from teleguard.codegraph.model import (
    CodeGraph,
    Edge,
    EdgeType,
    Evidence,
    Node,
    NodeType,
)
from teleguard.findings import NULL_LOOKALIKES, Finding, FindingKind


def field_id(name: str) -> str:
    return f"field:{name}"


def output_id(name: str) -> str:
    return f"out:{name}"


def function_id(module: str, func: str) -> str:
    return f"fn:{module}.{func}"


class _Module:
    def __init__(self, root: Path, path: Path) -> None:
        self.source = path.read_text()
        self.rel_path = path.relative_to(root).as_posix()
        parts = list(path.relative_to(root).with_suffix("").parts)
        self.name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts) or "__init__"
        self.package = ".".join(parts[:-1])
        self.tree = ast.parse(self.source, filename=str(path))
        self.constants: dict[str, Any] = {}
        self.aliases: dict[str, str] = {}
        for node in self.tree.body:
            self._collect(node)

    def _collect(self, node: ast.stmt) -> None:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    self.constants[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
        elif isinstance(node, ast.Import):
            for a in node.names:
                self.aliases[a.asname or a.name] = a.name
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_relative(self.package, node.module, node.level)
            for a in node.names:
                self.aliases[a.asname or a.name] = f"{base}.{a.name}" if base else a.name

    def functions(self) -> list[ast.FunctionDef]:
        return [n for n in self.tree.body if isinstance(n, ast.FunctionDef)]


def _resolve_relative(package: str, module: str | None, level: int) -> str:
    if level == 0:
        return module or ""
    parts = package.split(".") if package else []
    base = parts[: len(parts) - (level - 1)] if level > 1 else parts
    return ".".join([*base, module] if module else base)


def _internal_target(
    func: ast.expr, mod: _Module, by_name: dict[str, _Module]
) -> tuple[str, str] | None:
    if not isinstance(func, ast.Name):
        return None
    if any(f.name == func.id for f in mod.functions()):
        return mod.name, func.id
    qualified = mod.aliases.get(func.id, "")
    if "." in qualified:
        target_mod, symbol = qualified.rsplit(".", 1)
        if target_mod in by_name:
            return target_mod, symbol
    return None


class PythonPandasAdapter:
    name = "python_pandas"

    def __init__(self, entry: str | None = None) -> None:
        # "module.function" whose calls, in order, define the stages (e.g. "run.run").
        self.entry = entry

    def source_files(self, root: Path) -> list[Path]:
        return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)

    def analyze(self, root: Path) -> AnalysisResult:
        modules = [_Module(root, p) for p in self.source_files(root)]
        by_name = {m.name: m for m in modules}
        graph = CodeGraph()
        findings: list[Finding] = []

        for mod in modules:
            graph.add_node(Node(id=f"mod:{mod.name}", type=NodeType.MODULE, label=mod.name,
                                attrs={"file": mod.rel_path}))
        for mod in modules:
            self._add_imports(graph, mod, by_name)
            for func in mod.functions():
                graph.add_node(Node(id=function_id(mod.name, func.name), type=NodeType.FUNCTION,
                                    label=f"{mod.name}.{func.name}",
                                    attrs={"file": mod.rel_path, "line": func.lineno}))
        for mod in modules:
            for func in mod.functions():
                visitor = _FunctionVisitor(graph, mod, func, by_name)
                visitor.visit(func)
                findings.extend(visitor.findings)

        findings.extend(self._unused_fields(graph))
        stages = self._stages(graph, by_name)
        return AnalysisResult(graph=graph, findings=findings, stages=stages,
                              checkpoints=self._checkpoints(graph, stages))

    @staticmethod
    def _add_imports(graph: CodeGraph, mod: _Module, by_name: dict[str, _Module]) -> None:
        for target in {q.rsplit(".", 1)[0] for q in mod.aliases.values() if "." in q}:
            if target in by_name and target != mod.name:
                graph.add_edge(Edge(source=f"mod:{mod.name}", target=f"mod:{target}",
                                    type=EdgeType.IMPORTS))

    @staticmethod
    def _unused_fields(graph: CodeGraph) -> list[Finding]:
        consumed = {e.source for e in graph.edges
                    if e.type in (EdgeType.READS, EdgeType.DERIVES, EdgeType.PRODUCES)}
        findings = []
        for edge in graph.edges:
            if edge.type is EdgeType.WRITES and edge.target not in consumed and edge.evidence:
                name = graph.node(edge.target).label
                findings.append(Finding(
                    FindingKind.UNUSED_FIELD, name,
                    f"'{name}' is created but never used later and never reaches an output",
                    edge.evidence))
        return findings

    def _stages(self, graph: CodeGraph, by_name: dict[str, _Module]) -> list[str]:
        """Stages are the internal functions the entry function calls, in call order."""
        if not self.entry:
            return []
        mod_name, func_name = self.entry.rsplit(".", 1)
        mod = by_name[mod_name]
        entry = next(f for f in mod.functions() if f.name == func_name)
        stages: list[str] = []
        for stmt in entry.body:
            for call in (n for n in ast.walk(stmt) if isinstance(n, ast.Call)):
                target = _internal_target(call.func, mod, by_name)
                if not target:
                    continue
                stage_id = f"stage:{len(stages) + 1}:{target[1]}"
                graph.add_node(Node(id=stage_id, type=NodeType.STAGE, label=target[1], attrs={
                    "order": len(stages) + 1, "function": function_id(*target),
                    "called_at": f"{mod.rel_path}:{stmt.lineno}"}))
                graph.add_edge(Edge(source=stage_id, target=function_id(*target),
                                    type=EdgeType.CALLS))
                if stages:
                    graph.add_edge(Edge(source=stages[-1], target=stage_id,
                                        type=EdgeType.NEXT_STAGE))
                stages.append(stage_id)
        return stages

    @staticmethod
    def _checkpoints(graph: CodeGraph, stages: list[str]) -> list[Checkpoint]:
        return [
            Checkpoint(name=f"after_{graph.node(s).label}", after_stage=s,
                       attach=AttachMode.IN_PROCESS_HOOK,
                       location=str(graph.node(s).attrs["called_at"]))
            for s in stages
        ]


class _FunctionVisitor(ast.NodeVisitor):
    """Walks one function and records column reads/writes/derivations and findings."""

    def __init__(self, graph: CodeGraph, mod: _Module, func: ast.FunctionDef,
                 by_name: dict[str, _Module]) -> None:
        self.graph = graph
        self.mod = mod
        self.by_name = by_name
        self.fn_id = function_id(mod.name, func.name)
        self.findings: list[Finding] = []
        self.local_constants = self._local_constants(func)

    @staticmethod
    def _local_constants(func: ast.FunctionDef) -> dict[str, Any]:
        found: dict[str, Any] = {}
        for node in ast.walk(func):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                try:
                    found[node.targets[0].id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
        return found

    def _evidence(self, node: ast.AST) -> Evidence:
        line = getattr(node, "lineno", 0)
        snippet = self.mod.source.splitlines()[line - 1].strip() if line else ""
        return Evidence(file=self.mod.rel_path, line=line, snippet=snippet)

    def _constant(self, name: str) -> Any:
        if name in self.local_constants:
            return self.local_constants[name]
        if name in self.mod.constants:
            return self.mod.constants[name]
        qualified = self.mod.aliases.get(name, "")
        if "." in qualified:
            target, symbol = qualified.rsplit(".", 1)
            if target in self.by_name and symbol in self.by_name[target].constants:
                return self.by_name[target].constants[symbol]
        raise KeyError(name)

    def _value(self, node: ast.expr | None) -> Any:
        if node is None:
            raise KeyError("none")
        if isinstance(node, ast.Name):
            return self._constant(node.id)
        try:
            return ast.literal_eval(node)
        except ValueError as exc:
            raise KeyError(ast.unparse(node)) from exc

    def _columns(self, node: ast.expr | None) -> list[str]:
        try:
            value = self._value(node)
        except KeyError:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
            return list(value)
        return []

    def _column_of(self, expr: ast.expr) -> str | None:
        """The column a method chain starts from: df["x"].str.lower() -> "x"."""
        while True:
            if isinstance(expr, ast.Subscript):
                cols = self._columns(expr.slice)
                return cols[0] if len(cols) == 1 else None
            if isinstance(expr, (ast.Attribute, ast.Call)):
                expr = expr.value if isinstance(expr, ast.Attribute) else expr.func
            else:
                return None

    def _render(self, node: ast.expr) -> str:
        resolver = self

        class _Sub(ast.NodeTransformer):
            def visit_Name(self, n: ast.Name) -> ast.AST:
                try:
                    return ast.Constant(resolver._constant(n.id))
                except KeyError:
                    return n

        return ast.unparse(_Sub().visit(copy.deepcopy(node)))

    def _reads_in(self, node: ast.AST) -> list[str]:
        cols: list[str] = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Subscript) and isinstance(sub.ctx, ast.Load):
                cols += [c for c in self._columns(sub.slice) if c not in cols]
        return cols

    def _ensure(self, node_id: str, node_type: NodeType, label: str) -> str:
        if not self.graph.has_node(node_id):
            self.graph.add_node(Node(id=node_id, type=node_type, label=label))
        return node_id

    def _field(self, name: str) -> str:
        return self._ensure(field_id(name), NodeType.FIELD, name)

    def _output(self, name: str) -> str:
        return self._ensure(output_id(name), NodeType.OUTPUT, name)

    def _edge(self, source: str, target: str, kind: EdgeType, node: ast.AST,
              **attrs: Any) -> None:
        self.graph.add_edge(Edge(source=source, target=target, type=kind,
                                 evidence=self._evidence(node), attrs=attrs))

    def _find(self, kind: FindingKind, col: str | None, message: str, node: ast.AST) -> None:
        self.findings.append(Finding(kind, col, message, self._evidence(node)))

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.ctx, ast.Load):
            for col in self._columns(node.slice):
                self._edge(self._field(col), self.fn_id, EdgeType.READS, node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Subscript):
                for col in self._columns(target.slice):
                    self._write(col, node.value, node)
            elif isinstance(target, ast.Name):
                self._check_row_filter(target.id, node.value, node)
        self.generic_visit(node)

    def _write(self, col: str, value: ast.expr, node: ast.Assign) -> None:
        written = self._field(col)
        self._edge(self.fn_id, written, EdgeType.WRITES, node)
        formula = self._render(value)
        for src in self._reads_in(value):
            self._edge(self._field(src), written, EdgeType.DERIVES, node, formula=formula)
        if isinstance(value, ast.BinOp) and isinstance(value.op, (ast.Div, ast.Mult)):
            for side, other in ((value.right, value.left), (value.left, value.right)):
                try:
                    factor = self._value(side)
                except KeyError:
                    continue
                source_col = self._column_of(other)
                if isinstance(factor, (int, float)) and factor not in (0, 1) and source_col:
                    self._find(FindingKind.UNIT_CONVERSION, source_col,
                               f"'{col}' = {formula}: assumes '{source_col}' is in the unit "
                               f"that this factor ({factor}) converts from", node)

    def _check_row_filter(self, target: str, value: ast.expr, node: ast.Assign) -> None:
        while isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) \
                and value.func.attr == "copy":
            value = value.func.value
        if not isinstance(value, ast.Subscript) or self._columns(value.slice):
            return
        condition = value.slice
        cols = self._reads_in(condition)
        if not cols:
            return
        only_notna = (isinstance(condition, ast.Call) and isinstance(condition.func, ast.Attribute)
                      and condition.func.attr in ("notna", "notnull"))
        if not only_notna:
            self._find(FindingKind.ROW_FILTER, cols[0],
                       f"'{target}' keeps only rows where {self._render(condition)}; "
                       "other rows are dropped silently", node)
        for call in (n for n in ast.walk(condition) if isinstance(n, ast.Call)):
            if isinstance(call.func, ast.Attribute) and call.func.attr in ("notna", "notnull"):
                col = self._column_of(call.func.value)
                if col:
                    self._find(FindingKind.REQUIRED_FIELD, col,
                               f"rows with missing '{col}' are removed: '{col}' is treated "
                               "as required", node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        internal = _internal_target(func, self.mod, self.by_name)
        if internal:
            self._edge(self.fn_id, function_id(*internal), EdgeType.CALLS, node)
        if isinstance(func, ast.Attribute):
            handler = getattr(self, f"_call_{func.attr}", None)
            if handler:
                handler(node, func)
        self.generic_visit(node)

    @staticmethod
    def _kwarg(node: ast.Call, name: str) -> ast.expr | None:
        return next((k.value for k in node.keywords if k.arg == name), None)

    def _call_drop_duplicates(self, node: ast.Call, func: ast.Attribute) -> None:
        for col in self._columns(self._kwarg(node, "subset")):
            self._edge(self._field(col), self.fn_id, EdgeType.READS, node)
            self._find(FindingKind.DEDUP_KEY, col,
                       f"rows with the same '{col}' are treated as duplicates; "
                       "later copies are dropped", node)

    def _call_groupby(self, node: ast.Call, func: ast.Attribute) -> None:
        keys = self._columns(node.args[0] if node.args else self._kwarg(node, "by"))
        dropna = self._kwarg(node, "dropna")
        keeps_nulls = isinstance(dropna, ast.Constant) and dropna.value is False
        for col in keys:
            self._edge(self._field(col), self.fn_id, EdgeType.READS, node, role="group_key")
            self._edge(self._field(col), self._output(col), EdgeType.PRODUCES, node,
                       role="group_key")
            if not keeps_nulls:
                self._find(FindingKind.GROUP_KEY_DROPS_NULLS, col,
                           f"grouped by '{col}' with pandas' default dropna=True: rows with "
                           f"missing '{col}' vanish from the result", node)

    def _call_agg(self, node: ast.Call, func: ast.Attribute) -> None:
        receiver_col = self._column_of(func.value)
        for kw in node.keywords:
            if kw.arg is None:
                continue
            source: str | None = None
            how = ""
            if isinstance(kw.value, ast.Tuple) and len(kw.value.elts) == 2:
                cols = self._columns(kw.value.elts[0])
                source = cols[0] if cols else None
                how = self._render(kw.value.elts[1])
            elif receiver_col:
                source, how = receiver_col, self._render(kw.value)
            if source:
                out = self._output(kw.arg)
                self._edge(self._field(source), self.fn_id, EdgeType.READS, node)
                self._edge(self._field(source), out, EdgeType.PRODUCES, node, how=how)

    def _call_fillna(self, node: ast.Call, func: ast.Attribute) -> None:
        col = self._column_of(func.value)
        if col and node.args:
            self._find(FindingKind.DEFAULT_FILL, col,
                       f"missing values derived from '{col}' are silently replaced with "
                       f"{self._render(node.args[0])}", node)

    def _call_map(self, node: ast.Call, func: ast.Attribute) -> None:
        col = self._column_of(func.value)
        if not col or not node.args:
            return
        try:
            mapping = self._value(node.args[0])
        except KeyError:
            return
        if not isinstance(mapping, dict):
            return
        self._find(FindingKind.UNMAPPED_TO_NULL, col,
                   f"'{col}' is mapped with a fixed table of {len(mapping)} values "
                   f"({', '.join(map(str, list(mapping)[:8]))}); any other value becomes "
                   "missing", node)
        for key, val in mapping.items():
            if isinstance(val, str) and val in NULL_LOOKALIKES:
                self._find(FindingKind.NULL_LOOKALIKE_VALUE, col,
                           f"'{key}' maps to the text '{val}', which pandas and most CSV "
                           "readers load as missing: downstream consumers lose it", node)

    def _call_contains(self, node: ast.Call, func: ast.Attribute) -> None:
        col = self._column_of(func.value)
        if col and node.args:
            self._find(FindingKind.KEYWORD_MATCH, col,
                       f"'{col}' is classified by matching the text "
                       f"{self._render(node.args[0])}: wording or language changes break it",
                       node)

    def _call_split(self, node: ast.Call, func: ast.Attribute) -> None:
        col = self._column_of(func.value)
        if col:
            sep = self._render(node.args[0]) if node.args else "whitespace"
            self._find(FindingKind.STRING_FORMAT, col,
                       f"'{col}' is assumed to be text split by {sep}", node)

    def _call_to_datetime(self, node: ast.Call, func: ast.Attribute) -> None:
        unit = self._kwarg(node, "unit")
        col = self._column_of(node.args[0]) if node.args else None
        if col and unit is not None:
            self._find(FindingKind.TIMESTAMP_UNIT, col,
                       f"'{col}' is parsed as epoch time in {self._render(unit)}", node)
        utc = self._kwarg(node, "utc")
        if col and isinstance(utc, ast.Constant) and utc.value is True:
            self._find(FindingKind.TIMEZONE, col,
                       f"times from '{col}' are UTC: any daily grouping uses UTC days, "
                       "not local days", node)

    def _call_json_normalize(self, node: ast.Call, func: ast.Attribute) -> None:
        self._find(FindingKind.RUNTIME_COLUMNS, None,
                   "columns created here depend on the data, not the code; confirm them "
                   "with a runtime run", node)

    def _call_DataFrame(self, node: ast.Call, func: ast.Attribute) -> None:  # noqa: N802
        if node.args and not isinstance(node.args[0], (ast.Dict, ast.Constant)):
            self._find(FindingKind.RUNTIME_COLUMNS, None,
                       "a DataFrame is built from records: its column names come from the "
                       "data, not the code; confirm them with a runtime run", node)
