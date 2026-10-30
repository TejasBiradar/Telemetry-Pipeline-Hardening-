import { useCallback, useMemo, useState } from "react"
import type { OnboardGraph, OnboardGraphEdge, OnboardGraphNode } from "../api/client"

const NODE_W = 220
const NODE_H = 64
const GAP_X = 28
const GAP_Y = 36
const PAD = 24

interface StageCard {
  id: string
  label: string
  column: number
  row: number
  order: number
  writes: string[]
  reads: string[]
  outputUri: string
  x: number
  y: number
}

interface StageEdge {
  id: string
  x1: number
  y1: number
  x2: number
  y2: number
}

interface Layout {
  width: number
  height: number
  stages: StageCard[]
  edges: StageEdge[]
}

export function PipelineGraph({ graph }: { graph: OnboardGraph | undefined }) {
  const layout = useMemo(() => layoutStages(graph), [graph])
  const [picked, setPicked] = useState<string | null>(null)

  if (!layout || layout.stages.length === 0) {
    return <p className="flow-note">This registration has no stages in its code graph.</p>
  }

  const selected =
    layout.stages.find((stage) => stage.id === picked) ??
    layout.stages[0]

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
              <marker id="graph-stage-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0 0 L8 4 L0 8 Z" className="graph-arrow" />
              </marker>
            </defs>
            {layout.edges.map((edge) => (
              <path key={edge.id} d={edgePath(edge)} className="graph-edge" markerEnd="url(#graph-stage-arrow)" />
            ))}
          </svg>
          {layout.stages.map((stage) => (
            <StageNode
              key={stage.id}
              stage={stage}
              selected={stage.id === selected.id}
              onSelect={setPicked}
            />
          ))}
        </div>
        <p className="graph-legend">Select a stage. The line is the order the tasks run.</p>
      </div>
      <StageDetail stage={selected} />
    </div>
  )
}

function StageNode({
  stage,
  selected,
  onSelect,
}: {
  stage: StageCard
  selected: boolean
  onSelect: (id: string) => void
}) {
  const select = useCallback(() => onSelect(stage.id), [onSelect, stage.id])
  const className = [
    "graph-stage",
    selected ? "is-selected" : "",
    stage.outputUri ? "is-output" : "",
  ]
    .filter(Boolean)
    .join(" ")
  const meta = stage.outputUri
    ? "Writes a file"
    : stage.writes.length > 0
      ? `${stage.writes.length} fields`
      : "No fields"

  return (
    <button
      type="button"
      className={className}
      style={{ left: stage.x, top: stage.y, width: NODE_W, height: NODE_H }}
      aria-pressed={selected}
      title={stage.label}
      onClick={select}
    >
      <span className="graph-stage-index">{stage.order}</span>
      <span className="graph-stage-name">{stage.label}</span>
      <span className="graph-stage-meta">{meta}</span>
    </button>
  )
}

function StageDetail({ stage }: { stage: StageCard }) {
  return (
    <section className="graph-detail" aria-label={`${stage.label} fields`}>
      <div className="graph-detail-head">
        <h3 className="graph-detail-title">{stage.label}</h3>
        <span className="graph-stage-meta">{stage.outputUri ? "Writes a file" : "In memory"}</span>
      </div>
      {stage.outputUri ? <p className="graph-output mono">{stage.outputUri}</p> : null}
      {sameFields(stage.writes, stage.reads) ? (
        <FieldList title="Fields" fields={stage.writes} tone="write" />
      ) : (
        <>
          <FieldList title="Writes" fields={stage.writes} tone="write" />
          <FieldList title="Reads" fields={stage.reads} tone="read" />
        </>
      )}
    </section>
  )
}

function sameFields(left: string[], right: string[]): boolean {
  return left.length > 0 && left.length === right.length && left.every((field, index) => field === right[index])
}

function FieldList({ title, fields, tone }: { title: string; fields: string[]; tone: "write" | "read" }) {
  return (
    <div>
      <h4 className="graph-detail-label">{title}</h4>
      {fields.length === 0 ? (
        <p className="flow-note">None recorded</p>
      ) : (
        <ul className="graph-chips">
          {fields.map((field) => (
            <li key={field} className={`graph-chip graph-chip-${tone}`}>
              {field}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function layoutStages(graph: OnboardGraph | undefined): Layout | null {
  const nodes = graph?.nodes ?? []
  const edges = graph?.edges ?? []
  const stages = nodes.filter((node) => node.type === "stage")
  if (stages.length === 0) return null

  const rank = dependencyRank(stages, edges)
  const compact = compactColumns(rank)
  const cards = placeStages(stages, edges, nodes, rank, compact)
  const byId = new Map(cards.map((stage) => [stage.id, stage]))
  const drawn: StageEdge[] = []
  for (const edge of edges) {
    if (edge.type !== "next_stage") continue
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target) continue
    drawn.push({
      id: `${edge.source}:${edge.target}`,
      x1: source.x + NODE_W / 2,
      y1: source.y + NODE_H,
      x2: target.x + NODE_W / 2,
      y2: target.y,
    })
  }
  const columns = Math.max(...cards.map((stage) => stage.column), 0) + 1
  const rows = Math.max(...cards.map((stage) => stage.row), 0) + 1
  return {
    width: PAD * 2 + rows * NODE_W + Math.max(rows - 1, 0) * GAP_X,
    height: PAD * 2 + columns * NODE_H + Math.max(columns - 1, 0) * GAP_Y,
    stages: cards,
    edges: drawn,
  }
}

function placeStages(
  stages: OnboardGraphNode[],
  edges: OnboardGraphEdge[],
  nodes: OnboardGraphNode[],
  rank: Map<string, number>,
  compact: Map<number, number>,
): StageCard[] {
  const fields = fieldsByStage(edges, nodes)
  const grouped = new Map<number, OnboardGraphNode[]>()
  for (const stage of stages) {
    const column = compact.get(rank.get(stage.id) ?? 0) ?? 0
    const list = grouped.get(column) ?? []
    list.push(stage)
    grouped.set(column, list)
  }
  const placed: StageCard[] = []
  for (const [column, list] of grouped) {
    list.sort((left, right) => stageOrder(left) - stageOrder(right) || left.label.localeCompare(right.label))
    list.forEach((stage, row) => {
      const linked = fields.get(stage.id)
      const output = stage.attrs.output_uri
      placed.push({
        id: stage.id,
        label: stage.label,
        column,
        row,
        order: stageOrder(stage),
        writes: linked?.writes ?? [],
        reads: linked?.reads ?? [],
        outputUri: typeof output === "string" ? output : "",
        x: PAD + row * (NODE_W + GAP_X),
        y: PAD + column * (NODE_H + GAP_Y),
      })
    })
  }
  return placed.sort((left, right) => left.column - right.column || left.row - right.row)
}

function fieldsByStage(
  edges: OnboardGraphEdge[],
  nodes: OnboardGraphNode[],
): Map<string, { writes: string[]; reads: string[] }> {
  const labelOf = new Map(nodes.map((node) => [node.id, node.label]))
  const stageOfFunction = new Map<string, string>()
  for (const edge of edges) {
    if (edge.type === "calls") stageOfFunction.set(edge.target, edge.source)
  }
  const writes = new Map<string, Set<string>>()
  const reads = new Map<string, Set<string>>()
  for (const edge of edges) {
    if (edge.type === "writes") {
      const stage = stageOfFunction.get(edge.source)
      if (stage) addLabel(writes, stage, labelOf.get(edge.target) ?? edge.target)
    }
    if (edge.type === "reads") {
      const stage = stageOfFunction.get(edge.target)
      if (stage) addLabel(reads, stage, labelOf.get(edge.source) ?? edge.source)
    }
  }
  const stages = new Set([...writes.keys(), ...reads.keys()])
  return new Map(
    [...stages].map((stage) => [
      stage,
      {
        writes: sorted(writes.get(stage)),
        reads: sorted(reads.get(stage)),
      },
    ]),
  )
}

function addLabel(bucket: Map<string, Set<string>>, stage: string, label: string): void {
  const set = bucket.get(stage) ?? new Set<string>()
  set.add(label)
  bucket.set(stage, set)
}

function sorted(values: Set<string> | undefined): string[] {
  return [...(values ?? [])].sort((left, right) => left.localeCompare(right))
}

function dependencyRank(stages: OnboardGraphNode[], edges: OnboardGraphEdge[]): Map<string, number> {
  const rank = new Map(stages.map((stage) => [stage.id, 0]))
  for (let pass = 0; pass < stages.length; pass += 1) {
    let changed = false
    for (const edge of edges) {
      if (edge.type !== "next_stage") continue
      const next = (rank.get(edge.source) ?? 0) + 1
      if ((rank.get(edge.target) ?? 0) < next) {
        rank.set(edge.target, next)
        changed = true
      }
    }
    if (!changed) break
  }
  return rank
}

function compactColumns(rank: Map<string, number>): Map<number, number> {
  const orders = [...new Set(rank.values())].sort((left, right) => left - right)
  return new Map(orders.map((order, index) => [order, index]))
}

function stageOrder(node: OnboardGraphNode): number {
  const order = node.attrs.order
  return typeof order === "number" ? order : 0
}

function edgePath(edge: StageEdge): string {
  const mid = (edge.y1 + edge.y2) / 2
  return `M ${edge.x1} ${edge.y1} C ${edge.x1} ${mid}, ${edge.x2} ${mid}, ${edge.x2} ${edge.y2}`
}
