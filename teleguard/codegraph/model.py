"""Common code-graph format. Every adapter produces it; everything else consumes it.

Shared contract (CLAUDE.md rule 7). Lineage queries follow only data links
(derives / produces), never through function nodes: a function that touches many fields
would otherwise make every field look like it affects every output.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import networkx as nx
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    MODULE = "module"
    FUNCTION = "function"
    FIELD = "field"
    OUTPUT = "output"
    EXTERNAL = "external"
    STAGE = "stage"


class EdgeType(str, Enum):
    IMPORTS = "imports"
    CALLS = "calls"
    READS = "reads"  # field -> function that reads it
    WRITES = "writes"  # function -> field it creates
    DERIVES = "derives"  # field -> field computed from it
    PRODUCES = "produces"  # field -> pipeline output
    NEXT_STAGE = "next_stage"


LINEAGE_EDGES: frozenset[EdgeType] = frozenset({EdgeType.DERIVES, EdgeType.PRODUCES})


class Origin(str, Enum):
    STATIC = "static"  # seen in the code
    RUNTIME = "runtime"  # seen only when the pipeline ran
    BOTH = "both"


class Evidence(BaseModel, frozen=True):
    file: str
    line: int
    snippet: str = ""


class Node(BaseModel):
    id: str
    type: NodeType
    label: str
    attrs: dict[str, Any] = Field(default_factory=dict)
    origin: Origin = Origin.STATIC


class Edge(BaseModel):
    source: str
    target: str
    type: EdgeType
    evidence: Evidence | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    origin: Origin = Origin.STATIC

    def key(self) -> tuple[str, str, str, str, int]:
        ev = self.evidence
        return (self.source, self.target, self.type.value, ev.file if ev else "", ev.line if ev else 0)


class CodeGraph:
    def __init__(self) -> None:
        self.nodes: list[Node] = []
        self.edges: list[Edge] = []
        self._node_ids: dict[str, Node] = {}
        self._edge_keys: set[tuple[str, str, str, str, int]] = set()

    def add_node(self, node: Node) -> Node:
        """Add a node; if the id exists, the first one wins and is returned."""
        existing = self._node_ids.get(node.id)
        if existing:
            return existing
        self._node_ids[node.id] = node
        self.nodes.append(node)
        return node

    def add_edge(self, edge: Edge) -> None:
        if edge.key() not in self._edge_keys:
            self._edge_keys.add(edge.key())
            self.edges.append(edge)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._node_ids

    def node(self, node_id: str) -> Node:
        return self._node_ids[node_id]

    def _lineage_view(self) -> nx.DiGraph:
        view: nx.DiGraph = nx.DiGraph()
        view.add_nodes_from(self._node_ids)
        view.add_edges_from((e.source, e.target) for e in self.edges if e.type in LINEAGE_EDGES)
        return view

    def downstream(self, node_id: str, node_type: NodeType | None = None) -> list[Node]:
        """Nodes whose values are computed, directly or indirectly, from this node."""
        found = nx.descendants(self._lineage_view(), node_id)
        return self._pick(found, node_type)

    def upstream(self, node_id: str, node_type: NodeType | None = None) -> list[Node]:
        """Nodes this node's value is computed from, directly or indirectly."""
        found = nx.ancestors(self._lineage_view(), node_id)
        return self._pick(found, node_type)

    def _pick(self, ids: set[str], node_type: NodeType | None) -> list[Node]:
        nodes = [self._node_ids[i] for i in sorted(ids)]
        return [n for n in nodes if node_type is None or n.type is node_type]

    def to_json(self) -> dict[str, Any]:
        return {
            "nodes": [n.model_dump(mode="json") for n in self.nodes],
            "edges": [e.model_dump(mode="json") for e in self.edges],
        }
