"""Merge the static graph (what the code says) with a runtime trace (what actually flowed).

Field nodes are marked `static` (only in code), `both` (confirmed by the run) or `runtime`
(only appeared when running, e.g. columns built from the data). Edges between two fields are
`both` when the run observed both columns, otherwise they stay `static`.
"""

from __future__ import annotations

from dataclasses import dataclass

from teleguard.codegraph.model import CodeGraph, Edge, EdgeType, Node, NodeType, Origin
from teleguard.tracer import RuntimeTrace


@dataclass
class MergeReport:
    static_fields: int
    confirmed_fields: int
    runtime_only_fields: list[str]
    static_only_fields: list[str]
    field_edges: int
    confirmed_field_edges: int

    @property
    def field_agreement(self) -> float:
        """Share of the code's fields that the run also observed (0 to 1)."""
        return self.confirmed_fields / self.static_fields if self.static_fields else 0.0

    @property
    def edge_agreement(self) -> float:
        return self.confirmed_field_edges / self.field_edges if self.field_edges else 0.0


def merge(graph: CodeGraph, trace: RuntimeTrace) -> MergeReport:
    """Mark origins on the graph in place and return the agreement report."""
    observed = trace.observed_columns()
    static_fields = {n.label: n for n in graph.nodes if n.type is NodeType.FIELD}

    for name, node in static_fields.items():
        node.origin = Origin.BOTH if name in observed else Origin.STATIC

    outputs = {n.label: n for n in graph.nodes if n.type is NodeType.OUTPUT}
    for name, node in outputs.items():
        node.origin = Origin.BOTH if name in observed else Origin.STATIC

    runtime_only = sorted(observed - set(static_fields) - set(outputs))
    for name in runtime_only:
        graph.add_node(Node(id=f"field:{name}", type=NodeType.FIELD, label=name,
                            origin=Origin.RUNTIME))

    field_edges = [e for e in graph.edges if _is_field_edge(graph, e)]
    confirmed = 0
    for edge in field_edges:
        both = (graph.node(edge.source).origin is Origin.BOTH
                and graph.node(edge.target).origin is Origin.BOTH)
        if both:
            edge.origin = Origin.BOTH
            confirmed += 1

    return MergeReport(
        static_fields=len(static_fields),
        confirmed_fields=sum(1 for n in static_fields.values() if n.origin is Origin.BOTH),
        runtime_only_fields=runtime_only,
        static_only_fields=sorted(n for n, node in static_fields.items()
                                  if node.origin is Origin.STATIC),
        field_edges=len(field_edges),
        confirmed_field_edges=confirmed,
    )


def _is_field_edge(graph: CodeGraph, edge: Edge) -> bool:
    return (edge.type is EdgeType.DERIVES
            and graph.node(edge.source).type is NodeType.FIELD
            and graph.node(edge.target).type is NodeType.FIELD)
