import { useEffect, useState } from "react"
import type { CodeGraph, GraphNode, GraphEdge } from "../api/types"

interface StageGroup {
  name: string
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export function CodeGraphVisualizer({ analysis }: { analysis: CodeGraph | null }) {
  const [stageGroups, setStageGroups] = useState<StageGroup[]>([])

  useEffect(() => {
    if (!analysis) return

    // Group nodes/edges by stage
    const grouped = groupByStage(analysis)
    setStageGroups(grouped)
  }, [analysis])

  return (
    <div style={{ padding: "16px", background: "var(--surface)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: "var(--text)" }}>
        📊 Code Graph: Fields & Transformations
      </div>

      {stageGroups.length === 0 ? (
        <div style={{ color: "var(--text-muted)", fontSize: 12 }}>
          No graph data available
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {stageGroups.map((group, idx) => (
            <div key={idx}>
              <StageGroupCard stage={group} />
              {idx < stageGroups.length - 1 && (
                <div style={{ textAlign: "center", padding: "8px", color: "var(--text-muted)", fontSize: 12 }}>
                  ↓
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 24, fontSize: 11, color: "var(--text-muted)", lineHeight: "1.6" }}>
        <strong>How to read this:</strong>
        <div>🔑 Fields — data columns flowing through the pipeline</div>
        <div>→ derives — one field is computed from another</div>
        <div>→ produces — field becomes part of the output</div>
        <div>→ reads — field is used in a transformation</div>
      </div>
    </div>
  )
}

function groupByStage(graph: CodeGraph): StageGroup[] {
  const groups: StageGroup[] = []

  // Find all stages in the graph
  const stageNodes = graph.nodes.filter(n => n.type === "stage")

  if (stageNodes.length === 0) {
    // Fallback: show all nodes/edges in one group
    return [{
      name: "Pipeline",
      nodes: graph.nodes,
      edges: graph.edges,
    }]
  }

  // For each stage, find nodes that belong to it
  stageNodes.forEach(stageNode => {
    const stageName = stageNode.label

    // Find all nodes connected to this stage
    const stageEdges = graph.edges.filter(e =>
      e.source === stageNode.id || e.target === stageNode.id ||
      e.type === "next_stage"
    )

    // Find field nodes that are inputs/outputs of this stage
    const relatedNodeIds = new Set<string>()
    stageEdges.forEach(e => {
      if (e.source !== stageNode.id) relatedNodeIds.add(e.source)
      if (e.target !== stageNode.id) relatedNodeIds.add(e.target)
    })

    const relatedNodes = graph.nodes.filter(n => relatedNodeIds.has(n.id) || n.type === "field")
    const relatedEdges = graph.edges.filter(e =>
      (relatedNodeIds.has(e.source) && relatedNodeIds.has(e.target)) ||
      (e.source === stageNode.id || e.target === stageNode.id)
    )

    groups.push({
      name: stageName,
      nodes: relatedNodes,
      edges: relatedEdges,
    })
  })

  return groups
}

function StageGroupCard({ stage }: { stage: StageGroup }) {
  // Extract field nodes
  const fields = stage.nodes.filter(n => n.type === "field" || n.type === "output")

  // Find field transformations (derives edges)
  const transformations = stage.edges.filter(e => e.type === "derives" || e.type === "produces" || e.type === "reads")

  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-md)",
      background: "var(--surface-2)",
      padding: "12px",
    }}>
      <div style={{ fontWeight: 600, fontSize: 13, color: "var(--accent)", marginBottom: 12 }}>
        {stage.name}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* Fields */}
        <div>
          <div style={{ fontWeight: 600, fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>
            🔑 Fields ({fields.length})
          </div>
          <div style={{
            background: "var(--surface)",
            padding: "8px",
            borderRadius: "var(--radius-sm)",
            maxHeight: "150px",
            overflowY: "auto",
            fontSize: 10,
          }}>
            {fields.length > 0 ? (
              <ul style={{ margin: 0, paddingLeft: 16, color: "var(--text)" }}>
                {fields.map((f, i) => (
                  <li key={i} style={{ margin: "2px 0" }}>
                    {f.label} <span style={{ color: "var(--text-muted)", fontSize: 9 }}>({f.type})</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div style={{ color: "var(--text-muted)", fontStyle: "italic" }}>None</div>
            )}
          </div>
        </div>

        {/* Transformations */}
        <div>
          <div style={{ fontWeight: 600, fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>
            ⚙️ Transformations ({transformations.length})
          </div>
          <div style={{
            background: "var(--surface)",
            padding: "8px",
            borderRadius: "var(--radius-sm)",
            maxHeight: "150px",
            overflowY: "auto",
            fontSize: 10,
          }}>
            {transformations.length > 0 ? (
              <ul style={{ margin: 0, paddingLeft: 16, color: "var(--text)" }}>
                {transformations.map((e, i) => {
                  const srcLabel = stage.nodes.find(n => n.id === e.source)?.label || e.source
                  const tgtLabel = stage.nodes.find(n => n.id === e.target)?.label || e.target
                  return (
                    <li key={i} style={{ margin: "3px 0", lineHeight: "1.3" }}>
                      <span style={{ color: "var(--text-muted)", fontSize: 9 }}>{e.type}:</span><br/>
                      {srcLabel} → {tgtLabel}
                    </li>
                  )
                })}
              </ul>
            ) : (
              <div style={{ color: "var(--text-muted)", fontStyle: "italic" }}>None</div>
            )}
          </div>
        </div>
      </div>

      {/* Show edge evidence if available */}
      {transformations.some(e => e.evidence) && (
        <div style={{ marginTop: 8, fontSize: 9, color: "var(--text-muted)" }}>
          <strong>Evidence:</strong> Found in code at specific lines
        </div>
      )}
    </div>
  )
}
