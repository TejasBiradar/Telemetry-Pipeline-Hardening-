import { useMemo, useState } from "react"
import type { OnboardGraph, OnboardGraphEdge, OnboardGraphNode } from "../api/client"

const STAGE_W = 200
const STAGE_H = 76
const FIELD_W = 220
const FIELD_H = 68
const OUT_W = 200
const OUT_H = 56
const COL_GAP = 56
const STAGE_GAP = 40
const FIELD_GAP = 14
const PAD = 28

type GraphKind = "stage" | "field" | "output"
type EdgeKind = "next_stage" | "link" | "produces"

interface PlacedNode {
  id: string
  label: string
  kind: GraphKind
  x: number
  y: number
  w: number
  h: number
  order?: number
  meta?: string
  role?: string
  detail?: string
  expanded?: boolean
}

interface PlacedEdge {
  id: string
  kind: EdgeKind
  x1: number
  y1: number
  x2: number
  y2: number
}

interface Layout {
  width: number
  height: number
  nodes: PlacedNode[]
  edges: PlacedEdge[]
}

export function PipelineGraph({ graph }: { graph: OnboardGraph | undefined }) {
  const [expandedStageId, setExpandedStageId] = useState<string>("")
  const layout = useMemo(
    () => layoutGraph(graph, expandedStageId),
    [graph, expandedStageId],
  )

  if (!layout || layout.nodes.length === 0) {
    return <p className="flow-note">This registration has no stages in its code graph.</p>
  }

  return (
    <div className="graph-panel-body">
      <div className="graph-canvas">
        <div className="graph-board" style={{ width: layout.width, height: layout.height }}>
          <svg
            className="graph-edges"
            width={layout.width}
            height={layout.height}
            aria-hidden="true"
          >
            <defs>
              <marker id="graph-arrow-stage" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0 0 L8 4 L0 8 Z" className="graph-arrow" />
              </marker>
              <marker id="graph-arrow-data" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
                <path d="M0 0 L7 3.5 L0 7 Z" className="graph-arrow-data" />
              </marker>
            </defs>
            {layout.edges.map((edge) => (
              <path
                key={edge.id}
                d={edgePath(edge)}
                className={`graph-edge graph-edge-${edge.kind}`}
                markerEnd={
                  edge.kind === "next_stage"
                    ? "url(#graph-arrow-stage)"
                    : "url(#graph-arrow-data)"
                }
              />
            ))}
          </svg>
          {layout.nodes.map((node) => (
            <GraphNode
              key={node.id}
              node={node}
              onToggleStage={(stageId) => {
                setExpandedStageId((current) => (current === stageId ? "" : stageId))
              }}
            />
          ))}
        </div>
        <p className="graph-legend">
          Stages and columns come from this registration&apos;s code graph. Green = column this
          stage writes or reads. Peach = a pipeline output the graph links from that column
          (a produce edge), not “leaves this stage.”
        </p>
      </div>
    </div>
  )
}

function GraphNode({
  node,
  onToggleStage,
}: {
  node: PlacedNode
  onToggleStage: (stageId: string) => void
}) {
  if (node.kind === "stage") {
    return (
      <button
        type="button"
        className={`graph-stage graph-stage-button${node.expanded ? " is-selected" : ""}`}
        style={{ left: node.x, top: node.y, width: node.w, height: node.h }}
        title={node.expanded ? `Collapse ${node.label}` : `Expand ${node.label}`}
        aria-expanded={node.expanded === true}
        onClick={() => onToggleStage(node.id)}
      >
        <span className="graph-stage-index">{node.order ?? ""}</span>
        <strong className="graph-stage-name">{node.label}</strong>
        <span className="graph-stage-meta">{node.meta ?? "stage"}</span>
      </button>
    )
  }

  const className = [
    "graph-data-node",
    node.kind === "output" ? "is-output" : "is-field",
    node.role === "input" ? "is-input" : "",
    node.role === "adds" ? "is-adds" : "",
    node.role === "updates" ? "is-updates" : "",
  ]
    .filter(Boolean)
    .join(" ")
  const kindLabel =
    node.kind === "output"
      ? "Pipeline output"
      : node.role === "input"
        ? "Input to this stage"
        : node.role === "adds"
          ? "Added by this stage"
          : node.role === "updates"
            ? "Updated in this stage"
            : "Field"
  return (
    <div
      className={className}
      style={{ left: node.x, top: node.y, width: node.w, height: node.h }}
      title={node.detail ? `${node.label}: ${node.detail}` : `${node.label} — ${kindLabel}`}
    >
      <span className="graph-data-kind">{kindLabel}</span>
      <strong className="graph-data-label">{node.label}</strong>
      {node.detail ? <span className="graph-data-detail">{node.detail}</span> : null}
    </div>
  )
}

function layoutGraph(
  graph: OnboardGraph | undefined,
  expandedStageId: string,
): Layout | null {
  const nodes = graph?.nodes ?? []
  const edges = graph?.edges ?? []
  const stages = nodes
    .filter((node) => node.type === "stage")
    .slice()
    .sort((left, right) => stageOrder(left) - stageOrder(right) || left.label.localeCompare(right.label))
  if (stages.length === 0) return null

  const labelOf = new Map(nodes.map((node) => [node.id, displayLabel(node)]))
  const typeOf = new Map(nodes.map((node) => [node.id, node.type]))
  const links = stageFieldLinks(edges, typeOf)
  const formulas = formulasByField(edges)

  const placedStages: PlacedNode[] = []
  const stageCenterY = new Map<string, number>()
  let y = PAD
  stages.forEach((stage, index) => {
    const linked = links.get(stage.id)
    const fieldCount = linked
      ? new Set([...linked.writeIds, ...linked.readIds]).size
      : 0
    const outputCount = linked?.outputIds.size ?? 0
    const expanded = stage.id === expandedStageId
    const metaParts: string[] = [
      `${fieldCount} field${fieldCount === 1 ? "" : "s"}`,
    ]
    if (outputCount > 0) metaParts.push(`${outputCount} out`)
    metaParts.push(expanded ? "click to collapse" : "click to expand")

    placedStages.push({
      id: stage.id,
      label: displayLabel(stage),
      kind: "stage",
      x: PAD,
      y,
      w: STAGE_W,
      h: STAGE_H,
      order: typeof stage.attrs.order === "number" ? stage.attrs.order : index + 1,
      meta: metaParts.join(" · "),
      expanded,
    })
    stageCenterY.set(stage.id, y + STAGE_H / 2)
    y += STAGE_H + STAGE_GAP
  })

  const fieldColX = PAD + STAGE_W + COL_GAP
  const outColX = fieldColX + FIELD_W + COL_GAP
  const fieldNodes = new Map<string, PlacedNode>()
  const outputNodes = new Map<string, PlacedNode>()
  const expandedStage = stages.find((stage) => stage.id === expandedStageId)

  if (expandedStageId && expandedStage) {
    const linked = links.get(expandedStageId)
    const startY = (stageCenterY.get(expandedStageId) ?? PAD) - FIELD_H / 2
    let cursor = startY
    if (linked) {
      const fieldIds = orderedFieldIds(linked)
      const stageKey = displayLabel(expandedStage).toLowerCase()
      for (const fieldId of fieldIds) {
        const name = labelOf.get(fieldId) ?? shortId(fieldId)
        const role = fieldRole(linked, fieldId)
        const detail =
          role === "adds" || role === "updates"
            ? pickFormula(formulas.get(fieldId) ?? [], stageKey)
            : undefined
        fieldNodes.set(fieldId, {
          id: fieldId,
          label: name,
          kind: "field",
          role,
          detail,
          x: fieldColX,
          y: cursor,
          w: FIELD_W,
          h: FIELD_H,
        })
        cursor += FIELD_H + FIELD_GAP
      }

      for (const outputId of linked.outputIds) {
        const ownerField = [...linked.produceFrom.entries()].find(([, outs]) =>
          outs.has(outputId),
        )?.[0]
        const fieldY = ownerField ? fieldNodes.get(ownerField)?.y : undefined
        const anchorY = fieldY ?? cursor
        outputNodes.set(outputId, {
          id: outputId,
          label: labelOf.get(outputId) ?? shortId(outputId),
          kind: "output",
          role: "produces",
          x: outColX,
          y: anchorY,
          w: OUT_W,
          h: OUT_H,
        })
      }
    }
  }

  const placed = [...placedStages, ...fieldNodes.values(), ...outputNodes.values()]
  const byId = new Map(placed.map((node) => [node.id, node]))
  const drawn: PlacedEdge[] = []

  for (const edge of edges) {
    if (edge.type === "next_stage") {
      const source = byId.get(edge.source)
      const target = byId.get(edge.target)
      if (!source || !target) continue
      drawn.push(connect(source, target, "next_stage", "bottom", "top"))
    }
  }

  // One clean link from the expanded stage to each of its fields (no reverse reads,
  // no field-to-field derive fan-out — those caused the ghosted dashed lines).
  if (expandedStageId) {
    const linked = links.get(expandedStageId)
    const stage = byId.get(expandedStageId)
    if (linked && stage) {
      for (const fieldId of orderedFieldIds(linked)) {
        const field = byId.get(fieldId)
        if (!field) continue
        drawn.push(connect(stage, field, "link", "right", "left"))
      }
      for (const [fieldId, outs] of linked.produceFrom) {
        const field = byId.get(fieldId)
        if (!field) continue
        for (const outputId of outs) {
          const output = byId.get(outputId)
          if (!output) continue
          drawn.push(connect(field, output, "produces", "right", "left"))
        }
      }
    }
  }

  const maxRight = Math.max(...placed.map((node) => node.x + node.w), PAD)
  const maxBottom = Math.max(...placed.map((node) => node.y + node.h), PAD)
  return {
    width: maxRight + PAD,
    height: maxBottom + PAD,
    nodes: placed,
    edges: drawn,
  }
}

interface StageLinks {
  writeIds: Set<string>
  readIds: Set<string>
  outputIds: Set<string>
  produceFrom: Map<string, Set<string>>
}

interface FormulaHit {
  formula: string
  file: string
}

function stageFieldLinks(
  edges: OnboardGraphEdge[],
  typeOf: Map<string, string>,
): Map<string, StageLinks> {
  const stageOfFunction = new Map<string, string>()
  for (const edge of edges) {
    if (edge.type === "calls" && typeOf.get(edge.source) === "stage") {
      stageOfFunction.set(edge.target, edge.source)
    }
  }

  const byStage = new Map<string, StageLinks>()
  const ensure = (stageId: string): StageLinks => {
    const existing = byStage.get(stageId)
    if (existing) return existing
    const created: StageLinks = {
      writeIds: new Set(),
      readIds: new Set(),
      outputIds: new Set(),
      produceFrom: new Map(),
    }
    byStage.set(stageId, created)
    return created
  }

  const writtenBy = new Map<string, string>()
  for (const edge of edges) {
    if (edge.type === "writes") {
      const stage = stageOfFunction.get(edge.source)
      if (!stage) continue
      ensure(stage).writeIds.add(edge.target)
      writtenBy.set(edge.target, stage)
    }
    if (edge.type === "reads") {
      const stage = stageOfFunction.get(edge.target)
      if (!stage) continue
      ensure(stage).readIds.add(edge.source)
    }
  }

  for (const edge of edges) {
    if (edge.type !== "produces") continue
    const stage = writtenBy.get(edge.source)
    if (!stage) continue
    const linked = ensure(stage)
    linked.outputIds.add(edge.target)
    const outs = linked.produceFrom.get(edge.source) ?? new Set<string>()
    outs.add(edge.target)
    linked.produceFrom.set(edge.source, outs)
  }

  return byStage
}

function formulasByField(edges: OnboardGraphEdge[]): Map<string, FormulaHit[]> {
  const byField = new Map<string, FormulaHit[]>()
  for (const edge of edges) {
    if (edge.type !== "derives") continue
    const raw = edge.attrs?.formula
    if (typeof raw !== "string" || raw.trim().length === 0) continue
    const file = edge.evidence?.file ?? ""
    const list = byField.get(edge.target) ?? []
    list.push({ formula: raw, file })
    byField.set(edge.target, list)
  }
  return byField
}

function pickFormula(hits: FormulaHit[], stageKey: string): string | undefined {
  if (hits.length === 0) return undefined
  const staged =
    hits.find((hit) => hit.file.toLowerCase().includes(`${stageKey}.py`)) ??
    hits.find((hit) => hit.file.toLowerCase().includes(stageKey)) ??
    hits[0]
  return shortenFormula(staged.formula)
}

function shortenFormula(formula: string): string {
  let text = formula
    .replace(/\bsummary\[/g, "")
    .replace(/\bdf\[/g, "")
    .replace(/\]/g, "")
    .replace(/\.where\([^)]+\)/g, "")
    .replace(/\s+/g, " ")
    .trim()
  // cpm(spend_usd, impressions) → keep readable
  text = text.replace(/^cpm\((.+),\s*(.+)\)$/i, "$1 / $2 × 1000")
  text = text.replace(/^cpc\((.+),\s*(.+)\)$/i, "$1 / $2")
  text = text.replace(/^ctr\((.+),\s*(.+)\)$/i, "$1 / $2")
  if (text.length > 42) return `${text.slice(0, 39)}…`
  return text
}

function orderedFieldIds(linked: StageLinks): string[] {
  const writes = [...linked.writeIds].sort()
  const readsOnly = [...linked.readIds].filter((id) => !linked.writeIds.has(id)).sort()
  return [...writes, ...readsOnly]
}

function fieldRole(linked: StageLinks, fieldId: string): string {
  const writes = linked.writeIds.has(fieldId)
  const reads = linked.readIds.has(fieldId)
  if (writes && reads) return "updates"
  if (writes) return "adds"
  if (reads) return "input"
  return ""
}

function displayLabel(node: OnboardGraphNode): string {
  const label = typeof node.label === "string" ? node.label.trim() : ""
  if (label.length > 0) return label
  return shortId(node.id)
}

function shortId(id: string): string {
  const parts = id.split(":")
  return parts[parts.length - 1] || id
}

function connect(
  source: PlacedNode,
  target: PlacedNode,
  kind: EdgeKind,
  from: "right" | "bottom" | "left",
  to: "left" | "top" | "right",
): PlacedEdge {
  const start = anchor(source, from)
  const end = anchor(target, to)
  return {
    id: `${kind}:${source.id}:${target.id}`,
    kind,
    x1: start.x,
    y1: start.y,
    x2: end.x,
    y2: end.y,
  }
}

function anchor(node: PlacedNode, side: "left" | "right" | "top" | "bottom"): { x: number; y: number } {
  if (side === "left") return { x: node.x, y: node.y + node.h / 2 }
  if (side === "right") return { x: node.x + node.w, y: node.y + node.h / 2 }
  if (side === "top") return { x: node.x + node.w / 2, y: node.y }
  return { x: node.x + node.w / 2, y: node.y + node.h }
}

function edgePath(edge: PlacedEdge): string {
  if (edge.kind === "next_stage") {
    const mid = (edge.y1 + edge.y2) / 2
    return `M ${edge.x1} ${edge.y1} C ${edge.x1} ${mid}, ${edge.x2} ${mid}, ${edge.x2} ${edge.y2}`
  }
  const mid = (edge.x1 + edge.x2) / 2
  return `M ${edge.x1} ${edge.y1} C ${mid} ${edge.y1}, ${mid} ${edge.y2}, ${edge.x2} ${edge.y2}`
}

function stageOrder(node: OnboardGraphNode): number {
  const order = node.attrs.order
  return typeof order === "number" ? order : 0
}
