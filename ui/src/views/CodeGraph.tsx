import { useMemo, useState } from "react"
import dagre from "@dagrejs/dagre"
import { useGraph, useGuarantees } from "../api/hooks"
import { ErrorCard, LoadingCard } from "../components/QueryState"
import { StatusPill } from "../components/StatusPill"
import { toneForStatus } from "../components/statusTone"
import type { GraphEdge, GraphNode } from "../api/types"

const NODE_W = 150
const NODE_H = 36
// Impact analysis only means something over data flow: field -> field (derives) and
// field -> output (produces) — exactly what teleguard's own CodeGraph.downstream() follows
// (codegraph/model.py: LINEAGE_EDGES). Code-structure edges (calls, reads, writes, imports)
// are left out of this view on purpose; they answer "how is it computed", not "what breaks".
const LINEAGE_EDGE_TYPES = new Set(["derives", "produces"])

function layout(nodes: GraphNode[], edges: GraphEdge[]) {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: "LR", nodesep: 22, ranksep: 70 })
  g.setDefaultEdgeLabel(() => ({}))
  for (const n of nodes) g.setNode(n.id, { width: NODE_W, height: NODE_H })
  for (const e of edges) g.setEdge(e.source, e.target)
  dagre.layout(g)
  const positions = new Map<string, { x: number; y: number }>()
  for (const n of nodes) {
    const p = g.node(n.id)
    positions.set(n.id, { x: p.x, y: p.y })
  }
  return { positions, width: g.graph().width ?? 800, height: g.graph().height ?? 500 }
}

function reachable(adjacency: Map<string, string[]>, start: string): Set<string> {
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

export function CodeGraph() {
  const graph = useGraph()
  const guarantees = useGuarantees()
  const [selected, setSelected] = useState<string | null>(null)

  const lineage = useMemo(() => {
    if (!graph.data) return null
    const nodes = graph.data.nodes.filter((n) => n.type === "field" || n.type === "output")
    const nodeIds = new Set(nodes.map((n) => n.id))
    const edges = graph.data.edges.filter(
      (e) => LINEAGE_EDGE_TYPES.has(e.type) && nodeIds.has(e.source) && nodeIds.has(e.target),
    )
    const downstreamAdj = new Map<string, string[]>()
    const upstreamAdj = new Map<string, string[]>()
    for (const e of edges) {
      downstreamAdj.set(e.source, [...(downstreamAdj.get(e.source) ?? []), e.target])
      upstreamAdj.set(e.target, [...(upstreamAdj.get(e.target) ?? []), e.source])
    }
    const { positions, width, height } = layout(nodes, edges)
    return { nodes, edges, downstreamAdj, upstreamAdj, positions, width, height }
  }, [graph.data])

  if (graph.isLoading || guarantees.isLoading) return <div className="page"><LoadingCard /></div>
  if (graph.isError) return <div className="page"><ErrorCard error={graph.error} /></div>
  if (guarantees.isError) return <div className="page"><ErrorCard error={guarantees.error} /></div>
  if (!lineage) return null

  const downstream = selected ? reachable(lineage.downstreamAdj, selected) : new Set<string>()
  const upstream = selected ? reachable(lineage.upstreamAdj, selected) : new Set<string>()
  const selectedNode = lineage.nodes.find((n) => n.id === selected)
  const relatedGuarantees = selectedNode
    ? guarantees.data!.filter((g) => g.field === selectedNode.label)
    : []

  return (
    <div className="page">
      <div className="card-title">Field-level data flow</div>
      <div className="card-desc" style={{ marginBottom: 4 }}>
        Click a field to see what depends on it downstream, and what it depends on upstream —
        this is the blast radius you're reasoning about before any change.
      </div>

      <div className="graph-wrap">
        <svg
          viewBox={`0 0 ${lineage.width + 40} ${lineage.height + 40}`}
          width="100%"
          style={{ minWidth: 900, display: "block" }}
        >
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0L10 5L0 10z" fill="var(--text-faint)" />
            </marker>
          </defs>
          <g transform="translate(20,20)">
            {lineage.edges.map((e, i) => {
              const a = lineage.positions.get(e.source)!
              const b = lineage.positions.get(e.target)!
              const relevant = (id: string) => id === selected || upstream.has(id) || downstream.has(id)
              const involved = selected ? relevant(e.source) && relevant(e.target) : false
              return (
                <line
                  key={i}
                  x1={a.x + NODE_W / 2}
                  y1={a.y}
                  x2={b.x - NODE_W / 2}
                  y2={b.y}
                  stroke={involved ? "var(--accent)" : "var(--border-strong)"}
                  strokeWidth={involved ? 2 : 1.3}
                  opacity={selected && !involved ? 0.25 : 1}
                  markerEnd="url(#arrow)"
                />
              )
            })}
            {lineage.nodes.map((n) => {
              const p = lineage.positions.get(n.id)!
              const isSelected = n.id === selected
              const isDownstream = downstream.has(n.id)
              const isUpstream = upstream.has(n.id)
              const dim = selected && !isSelected && !isDownstream && !isUpstream
              const fill = n.type === "output" ? "var(--data-soft)" : "var(--surface-2)"
              const stroke = isSelected
                ? "var(--accent)"
                : isDownstream
                  ? "var(--warning)"
                  : isUpstream
                    ? "var(--accent-strong)"
                    : "var(--border-strong)"
              return (
                <g
                  key={n.id}
                  transform={`translate(${p.x - NODE_W / 2},${p.y - NODE_H / 2})`}
                  onClick={() => setSelected(n.id === selected ? null : n.id)}
                  style={{ cursor: "pointer", opacity: dim ? 0.3 : 1 }}
                >
                  <rect width={NODE_W} height={NODE_H} rx={8} fill={fill} stroke={stroke} strokeWidth={isSelected ? 2 : 1.3} />
                  <text
                    x={NODE_W / 2}
                    y={NODE_H / 2 + 4}
                    textAnchor="middle"
                    fontFamily="var(--font-mono)"
                    fontSize={11}
                    fill="var(--text)"
                  >
                    {n.label.length > 18 ? n.label.slice(0, 17) + "…" : n.label}
                  </text>
                </g>
              )
            })}
          </g>
        </svg>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="card-title">Impact analysis</div>
          {selectedNode ? (
            <>
              <div className="card-desc">{selectedNode.label} selected</div>
              <div style={{ marginTop: 12 }}>
                <div className="stat-label">Downstream dependents</div>
                <div className="stat-value" style={{ color: downstream.size > 0 ? "var(--warning)" : undefined }}>
                  {downstream.size}
                </div>
              </div>
              {downstream.size > 0 && (
                <p style={{ marginTop: 10, fontSize: 12.5, color: "var(--text-muted)" }}>
                  Affects: {[...downstream].map((id) => lineage.nodes.find((n) => n.id === id)?.label).join(", ")}
                </p>
              )}
            </>
          ) : (
            <div className="card-desc">Click a field in the graph above.</div>
          )}
        </div>

        <div className="card">
          <div className="card-title">Reconstructed guarantees for this field</div>
          {!selectedNode && <div className="card-desc">Select a field to see what the code assumes about it.</div>}
          {selectedNode && relatedGuarantees.length === 0 && (
            <div className="card-desc">No candidate findings recorded for this field.</div>
          )}
          <div style={{ marginTop: relatedGuarantees.length ? 10 : 0, display: "flex", flexDirection: "column", gap: 10 }}>
            {relatedGuarantees.map((g) => (
              <div key={g.id} style={{ paddingBottom: 10, borderBottom: "1px solid var(--border)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{g.kind}</span>
                  <StatusPill tone={toneForStatus(g.status)} label={g.status} />
                </div>
                <p style={{ fontSize: 13, marginTop: 6 }}>{g.message}</p>
                <p className="mono" style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 4 }}>
                  {g.file}:{g.line}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
