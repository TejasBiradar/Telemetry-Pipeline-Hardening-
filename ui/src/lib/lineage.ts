import type { CodeGraph, GraphEdge, GraphNode } from "../api/types"

// Impact analysis only means something over data flow: field -> field (derives) and
// field -> output (produces), the same edges teleguard's CodeGraph.downstream() follows
// (codegraph/model.py: LINEAGE_EDGE_TYPES). Code-structure edges are left out on purpose.
export const LINEAGE_EDGE_TYPES = new Set(["derives", "produces"])

export interface Lineage {
  nodes: GraphNode[]
  edges: GraphEdge[]
  downstreamAdj: Map<string, string[]>
  upstreamAdj: Map<string, string[]>
}

export function buildLineage(graph: CodeGraph): Lineage {
  const nodes = graph.nodes.filter((n) => n.type === "field" || n.type === "output")
  const nodeIds = new Set(nodes.map((n) => n.id))
  const edges = graph.edges.filter(
    (e) => LINEAGE_EDGE_TYPES.has(e.type) && nodeIds.has(e.source) && nodeIds.has(e.target),
  )
  const downstreamAdj = new Map<string, string[]>()
  const upstreamAdj = new Map<string, string[]>()
  for (const e of edges) {
    downstreamAdj.set(e.source, [...(downstreamAdj.get(e.source) ?? []), e.target])
    upstreamAdj.set(e.target, [...(upstreamAdj.get(e.target) ?? []), e.source])
  }
  return { nodes, edges, downstreamAdj, upstreamAdj }
}

export function reachable(adjacency: Map<string, string[]>, start: string): Set<string> {
  const seen = new Set<string>()
  const queue = [start]
  while (queue.length) {
    const current = queue.shift()!
    for (const next of adjacency.get(current) ?? []) {
      if (!seen.has(next)) {
        seen.add(next)
        queue.push(next)
      }
    }
  }
  return seen
}

/** Labels of the outputs a bad value in `fieldLabel` can reach; empty if the field is unknown. */
export function affectedOutputLabels(lineage: Lineage, fieldLabel: string): string[] {
  const start = lineage.nodes.find((n) => n.type === "field" && n.label === fieldLabel)
  if (!start) return []
  const hit = reachable(lineage.downstreamAdj, start.id)
  return lineage.nodes.filter((n) => n.type === "output" && hit.has(n.id)).map((n) => n.label)
}
