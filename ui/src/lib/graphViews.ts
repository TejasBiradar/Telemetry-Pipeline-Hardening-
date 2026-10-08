import type { CodeGraph, GraphEdge, GraphNode } from "../api/types"

export interface FieldTransform {
  source: string
  target: string
  snippet: string
  file: string | null
  line: number | null
}

export interface StageSummary {
  id: string
  order: number
  label: string
  functionLabel: string
  calledAt: string
  file: string
  reads: string[]
  writes: string[]
  transforms: FieldTransform[]
  produces: string[]
}

function labelOf(nodes: Map<string, GraphNode>, id: string): string {
  return nodes.get(id)?.label ?? id
}

function evidenceOf(edge: GraphEdge): { snippet: string; file: string | null; line: number | null } {
  if (!edge.evidence) return { snippet: "", file: null, line: null }
  return {
    snippet: edge.evidence.snippet?.trim() ?? "",
    file: edge.evidence.file,
    line: edge.evidence.line,
  }
}

/** Build per-stage summaries from the full analysis graph (not just field lineage). */
export function buildStageSummaries(graph: CodeGraph): StageSummary[] {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]))
  const stages = graph.nodes
    .filter((n) => n.type === "stage")
    .sort((a, b) => Number(a.attrs.order ?? 0) - Number(b.attrs.order ?? 0))

  return stages.map((stage) => {
    const fnId = String(stage.attrs.function ?? "")
    const fnNode = byId.get(fnId)
    const fnFile = String(fnNode?.attrs.file ?? "")
    const reads = new Set<string>()
    const writes = new Set<string>()
    const produces = new Set<string>()
    const transforms: FieldTransform[] = []

    for (const edge of graph.edges) {
      if (edge.type === "reads" && edge.target === fnId && byId.get(edge.source)?.type === "field") {
        reads.add(labelOf(byId, edge.source))
      }
      if (edge.type === "writes" && edge.source === fnId && byId.get(edge.target)?.type === "field") {
        writes.add(labelOf(byId, edge.target))
      }
      if (
        edge.type === "derives" &&
        byId.get(edge.source)?.type === "field" &&
        byId.get(edge.target)?.type === "field"
      ) {
        const wroteTarget = graph.edges.some(
          (w) => w.type === "writes" && w.source === fnId && w.target === edge.target,
        )
        if (wroteTarget) {
          const ev = evidenceOf(edge)
          transforms.push({
            source: labelOf(byId, edge.source),
            target: labelOf(byId, edge.target),
            snippet: ev.snippet,
            file: ev.file,
            line: ev.line,
          })
        }
      }
      if (edge.type === "produces" && byId.get(edge.target)?.type === "output") {
        const src = edge.source
        const tiedToFn =
          graph.edges.some((w) => w.type === "writes" && w.source === fnId && w.target === src) ||
          graph.edges.some((w) => w.type === "reads" && w.target === fnId && w.source === src)
        const ev = evidenceOf(edge)
        const sameFile = Boolean(fnFile && ev.file && ev.file === fnFile)
        if (tiedToFn || sameFile) {
          produces.add(labelOf(byId, edge.target))
        }
      }
    }

    return {
      id: stage.id,
      order: Number(stage.attrs.order ?? 0),
      label: stage.label,
      functionLabel: labelOf(byId, fnId),
      calledAt: String(stage.attrs.called_at ?? ""),
      file: fnFile,
      reads: [...reads].sort(),
      writes: [...writes].sort(),
      transforms,
      produces: [...produces].sort(),
    }
  })
}

export function pipelineOutputs(graph: CodeGraph): GraphNode[] {
  return graph.nodes.filter((n) => n.type === "output")
}

export function edgeTypeLabel(type: GraphEdge["type"]): string {
  switch (type) {
    case "derives":
      return "derives"
    case "produces":
      return "→ output"
    case "reads":
      return "reads"
    case "writes":
      return "writes"
    case "calls":
      return "calls"
    case "next_stage":
      return "next"
    case "imports":
      return "imports"
    default:
      return type
  }
}
