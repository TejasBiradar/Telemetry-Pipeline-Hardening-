import { useMemo, useState } from "react"
import dagre from "@dagrejs/dagre"
import { useGraph, useGuarantees } from "../api/hooks"
import { ErrorCard, LoadingCard } from "../components/QueryState"
import { StatusPill } from "../components/StatusPill"
import { toneForStatus } from "../components/statusTone"
import { buildLineage, reachable } from "../lib/lineage"
import { buildStageSummaries, edgeTypeLabel, pipelineOutputs } from "../lib/graphViews"
import type { GraphEdge, GraphNode, Guarantee } from "../api/types"

type ViewMode = "stages" | "lineage" | "swimlanes"

const NODE_W = 168
const NODE_H = 44

function layout(nodes: GraphNode[], edges: GraphEdge[]) {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: "LR", nodesep: 32, ranksep: 100 })
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

function edgePath(
  ax: number,
  ay: number,
  bx: number,
  by: number,
): string {
  const x1 = ax + NODE_W / 2
  const x2 = bx - NODE_W / 2
  const mid = (x1 + x2) / 2
  return `M ${x1} ${ay} C ${mid} ${ay}, ${mid} ${by}, ${x2} ${by}`
}

function Chip({ children, tone = "neutral" }: { children: string; tone?: "neutral" | "write" | "read" | "out" }) {
  const cls =
    tone === "write"
      ? "graph-chip graph-chip-write"
      : tone === "read"
        ? "graph-chip graph-chip-read"
        : tone === "out"
          ? "graph-chip graph-chip-out"
          : "graph-chip"
  return <span className={cls}>{children}</span>
}

function ViewToggle({ mode, onChange }: { mode: ViewMode; onChange: (m: ViewMode) => void }) {
  const opts: { id: ViewMode; label: string }[] = [
    { id: "stages", label: "Pipeline stages" },
    { id: "lineage", label: "Field lineage" },
    { id: "swimlanes", label: "Stage × fields" },
  ]
  return (
    <div className="view-tabs" role="tablist" aria-label="Code graph view">
      {opts.map((o) => (
        <button
          key={o.id}
          type="button"
          role="tab"
          className="view-tab"
          aria-selected={mode === o.id}
          onClick={() => onChange(o.id)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function StagesView({
  stages,
  outputs,
  selectedStage,
  onSelect,
}: {
  stages: ReturnType<typeof buildStageSummaries>
  outputs: GraphNode[]
  selectedStage: string | null
  onSelect: (id: string | null) => void
}) {
  const active = stages.find((s) => s.id === selectedStage) ?? null
  return (
    <div>
      <div className="stage-rail">
        {stages.map((stage, idx) => {
          const selected = stage.id === selectedStage
          return (
            <div key={stage.id} style={{ display: "flex", alignItems: "center" }}>
              <button
                type="button"
                className={"stage-card" + (selected ? " is-selected" : "")}
                onClick={() => onSelect(selected ? null : stage.id)}
              >
                <div className="stage-card-order">STAGE {stage.order}</div>
                <div className="stage-card-title">{stage.label}</div>
                <div className="stage-card-fn">{stage.functionLabel}</div>
                <div className="stage-card-meta">
                  {stage.writes.length} writes · {stage.reads.length} reads · {stage.produces.length} outputs
                </div>
              </button>
              {idx < stages.length - 1 && <div className="stage-arrow" aria-hidden="true">→</div>}
            </div>
          )
        })}
      </div>

      {active ? (
        <div className="card">
          <div className="card-title">
            What <span className="mono">{active.label}</span> does
          </div>
          <div className="card-desc">
            {active.calledAt ? `Called at ${active.calledAt}` : active.functionLabel}
            {active.file ? ` · ${active.file}` : ""}
          </div>

          <div className="grid grid-2" style={{ marginTop: 16 }}>
            <div>
              <div className="stat-label">Reads</div>
              <div style={{ marginTop: 8 }}>
                {active.reads.length === 0 && (
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>None detected</span>
                )}
                {active.reads.map((f) => (
                  <Chip key={f} tone="read">{f}</Chip>
                ))}
              </div>
            </div>
            <div>
              <div className="stat-label">Writes</div>
              <div style={{ marginTop: 8 }}>
                {active.writes.length === 0 && (
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>None detected</span>
                )}
                {active.writes.map((f) => (
                  <Chip key={f} tone="write">{f}</Chip>
                ))}
              </div>
            </div>
          </div>

          <div style={{ marginTop: 18 }}>
            <div className="stat-label">Transforms in this stage</div>
            {active.transforms.length === 0 ? (
              <div className="card-desc" style={{ marginTop: 8 }}>
                No field derivations attributed to this stage.
              </div>
            ) : (
              <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 10 }}>
                {active.transforms.map((t, i) => (
                  <div key={`${t.source}-${t.target}-${i}`} className="transform-block">
                    <div style={{ fontSize: 13, fontWeight: 650 }}>
                      <span className="mono">{t.source}</span>
                      <span style={{ color: "var(--accent)", margin: "0 8px" }}>→</span>
                      <span className="mono">{t.target}</span>
                    </div>
                    {t.snippet && (
                      <pre
                        className="mono"
                        style={{
                          marginTop: 8,
                          fontSize: 11,
                          whiteSpace: "pre-wrap",
                          color: "var(--text-muted)",
                          marginBottom: 0,
                        }}
                      >
                        {t.snippet}
                      </pre>
                    )}
                    {t.file && (
                      <div className="mono" style={{ fontSize: 10, color: "var(--text-faint)", marginTop: 6 }}>
                        {t.file}:{t.line}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {active.produces.length > 0 && (
            <div style={{ marginTop: 18 }}>
              <div className="stat-label">Outputs from this stage</div>
              <div style={{ marginTop: 8 }}>
                {active.produces.map((f) => (
                  <Chip key={f} tone="out">{f}</Chip>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="card">
          <div className="card-title">Pipeline outputs</div>
          <div className="card-desc">
            Click a stage to inspect reads, writes, and transforms. Final outputs:
          </div>
          <div style={{ marginTop: 10 }}>
            {outputs.map((o) => (
              <Chip key={o.id} tone="out">{o.label}</Chip>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function SwimlanesView({ stages }: { stages: ReturnType<typeof buildStageSummaries> }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${Math.max(stages.length, 1)}, minmax(230px, 1fr))`,
          gap: 14,
        }}
      >
        {stages.map((stage) => (
          <div key={stage.id} className="swim-col">
            <div className="swim-col-head">
              <div className="stage-card-order">STAGE {stage.order}</div>
              <div className="stage-card-title" style={{ fontSize: 16 }}>{stage.label}</div>
              <div className="stage-card-fn">{stage.functionLabel}</div>
            </div>
            <div className="swim-col-body">
              <div className="stat-label">Writes</div>
              <div style={{ marginTop: 6, marginBottom: 14 }}>
                {stage.writes.length === 0 && (
                  <span style={{ fontSize: 11, color: "var(--text-faint)" }}>—</span>
                )}
                {stage.writes.map((f) => (
                  <div key={f} style={{ marginBottom: 4 }}>
                    <Chip tone="write">{f}</Chip>
                  </div>
                ))}
              </div>
              <div className="stat-label">Key transforms</div>
              <div style={{ marginTop: 6 }}>
                {stage.transforms.length === 0 && (
                  <span style={{ fontSize: 11, color: "var(--text-faint)" }}>—</span>
                )}
                {stage.transforms.map((t, i) => (
                  <div key={i} className="mono" style={{ fontSize: 11, marginBottom: 6 }}>
                    {t.source} → {t.target}
                  </div>
                ))}
              </div>
              {stage.produces.length > 0 && (
                <>
                  <div className="stat-label" style={{ marginTop: 14 }}>Outputs</div>
                  <div style={{ marginTop: 6 }}>
                    {stage.produces.map((f) => (
                      <div key={f} style={{ marginBottom: 4 }}>
                        <Chip tone="out">{f}</Chip>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function LineageView({
  nodes,
  edges,
  positions,
  width,
  height,
  selected,
  onSelect,
  downstream,
  upstream,
}: {
  nodes: GraphNode[]
  edges: GraphEdge[]
  positions: Map<string, { x: number; y: number }>
  width: number
  height: number
  selected: string | null
  onSelect: (id: string | null) => void
  downstream: Set<string>
  upstream: Set<string>
}) {
  return (
    <div className="graph-wrap">
      <svg viewBox={`0 0 ${width + 48} ${height + 48}`} width="100%" style={{ minWidth: 920, display: "block" }}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0L10 5L0 10z" fill="var(--border-strong)" />
          </marker>
          <marker id="arrow-hot" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0L10 5L0 10z" fill="var(--accent)" />
          </marker>
          <filter id="nodeShadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="1" stdDeviation="1.2" floodOpacity="0.12" />
          </filter>
        </defs>
        <g transform="translate(24,24)">
          {edges.map((e, i) => {
            const a = positions.get(e.source)!
            const b = positions.get(e.target)!
            const relevant = (id: string) => id === selected || upstream.has(id) || downstream.has(id)
            const involved = selected ? relevant(e.source) && relevant(e.target) : false
            const mx = (a.x + b.x) / 2
            const my = (a.y + b.y) / 2
            return (
              <g key={i} opacity={selected && !involved ? 0.18 : 1}>
                <path
                  d={edgePath(a.x, a.y, b.x, b.y)}
                  fill="none"
                  stroke={involved ? "var(--accent)" : "var(--border-strong)"}
                  strokeWidth={involved ? 2.2 : 1.4}
                  markerEnd={involved ? "url(#arrow-hot)" : "url(#arrow)"}
                />
                <rect
                  x={mx - 28}
                  y={my - 16}
                  width={56}
                  height={14}
                  rx={4}
                  fill="var(--surface)"
                  opacity={0.92}
                />
                <text
                  x={mx}
                  y={my - 5}
                  textAnchor="middle"
                  fontSize={9}
                  fill="var(--text-faint)"
                  fontFamily="var(--font-mono)"
                >
                  {edgeTypeLabel(e.type)}
                </text>
              </g>
            )
          })}
          {nodes.map((n) => {
            const p = positions.get(n.id)!
            const isSelected = n.id === selected
            const isDownstream = downstream.has(n.id)
            const isUpstream = upstream.has(n.id)
            const dim = selected && !isSelected && !isDownstream && !isUpstream
            const fill = n.type === "output" ? "var(--data-soft)" : "var(--surface)"
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
                onClick={() => onSelect(n.id === selected ? null : n.id)}
                style={{ cursor: "pointer", opacity: dim ? 0.28 : 1 }}
                filter="url(#nodeShadow)"
              >
                <title>{`${n.type}: ${n.label}`}</title>
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx={10}
                  fill={fill}
                  stroke={stroke}
                  strokeWidth={isSelected ? 2.2 : 1.3}
                />
                <text x={12} y={15} fontSize={9} fill="var(--text-faint)" fontFamily="var(--font-ui)">
                  {n.type}
                </text>
                <text
                  x={NODE_W / 2}
                  y={NODE_H / 2 + 11}
                  textAnchor="middle"
                  fontFamily="var(--font-mono)"
                  fontSize={11.5}
                  fill="var(--text)"
                >
                  {n.label.length > 18 ? `${n.label.slice(0, 17)}…` : n.label}
                </text>
              </g>
            )
          })}
        </g>
      </svg>
      <div style={{ padding: "12px 16px", fontSize: 11.5, color: "var(--text-muted)", borderTop: "1px solid var(--border)" }}>
        Curved edges show data flow · amber nodes are outputs · click a field for blast radius
      </div>
    </div>
  )
}

function GuaranteeRow({ g }: { g: Guarantee }) {
  return (
    <div style={{ paddingBottom: 12, borderBottom: "1px solid var(--border)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <span className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{g.kind}</span>
        <StatusPill tone={toneForStatus(g.status)} label={g.status} />
      </div>
      <p style={{ fontSize: 13, marginTop: 6 }}>{g.message}</p>
      <p className="mono" style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 4 }}>
        {g.file}:{g.line}
      </p>
    </div>
  )
}

export function CodeGraph() {
  const graph = useGraph()
  const guarantees = useGuarantees()
  const [mode, setMode] = useState<ViewMode>("stages")
  const [selectedField, setSelectedField] = useState<string | null>(null)
  const [selectedStage, setSelectedStage] = useState<string | null>(null)

  const stages = useMemo(
    () => (graph.data ? buildStageSummaries(graph.data) : []),
    [graph.data],
  )
  const outputs = useMemo(
    () => (graph.data ? pipelineOutputs(graph.data) : []),
    [graph.data],
  )

  const lineage = useMemo(() => {
    if (!graph.data) return null
    const built = buildLineage(graph.data)
    const laid = layout(built.nodes, built.edges)
    return { ...built, ...laid }
  }, [graph.data])

  if (graph.isLoading || guarantees.isLoading) return <div className="page"><LoadingCard /></div>
  if (graph.isError) return <div className="page"><ErrorCard error={graph.error} /></div>
  if (guarantees.isError) return <div className="page"><ErrorCard error={guarantees.error} /></div>
  if (!graph.data || !lineage) return null

  const downstream = selectedField ? reachable(lineage.downstreamAdj, selectedField) : new Set<string>()
  const upstream = selectedField ? reachable(lineage.upstreamAdj, selectedField) : new Set<string>()
  const selectedNode = lineage.nodes.find((n) => n.id === selectedField)
  const relatedGuarantees = selectedNode
    ? guarantees.data!.filter((g) => g.field === selectedNode.label)
    : []

  const stageName = stages.find((s) => s.id === selectedStage)?.label
  const stageGuarantees = selectedStage
    ? guarantees.data!.filter((g) => {
        const stage = stages.find((s) => s.id === selectedStage)
        if (!stage) return false
        const fields = new Set([...stage.reads, ...stage.writes, ...stage.produces])
        return g.field != null && fields.has(g.field)
      })
    : []

  return (
    <div className="page">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div>
          <div className="card-title" style={{ fontSize: 18 }}>Code graph</div>
          <div className="card-desc" style={{ marginBottom: 0, maxWidth: 640 }}>
            Generated on the fly from the active pipeline. Stages explain structure; lineage
            shows blast radius when a field goes wrong.
          </div>
        </div>
        <ViewToggle
          mode={mode}
          onChange={(m) => {
            setMode(m)
            setSelectedField(null)
          }}
        />
      </div>

      <div>
        {mode === "stages" && (
          <StagesView
            stages={stages}
            outputs={outputs}
            selectedStage={selectedStage}
            onSelect={setSelectedStage}
          />
        )}
        {mode === "swimlanes" && <SwimlanesView stages={stages} />}
        {mode === "lineage" && (
          <LineageView
            nodes={lineage.nodes}
            edges={lineage.edges}
            positions={lineage.positions}
            width={lineage.width}
            height={lineage.height}
            selected={selectedField}
            onSelect={setSelectedField}
            downstream={downstream}
            upstream={upstream}
          />
        )}
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="card-title">
            {mode === "lineage" ? "Impact analysis" : "Stage findings"}
          </div>
          {mode === "lineage" ? (
            selectedNode ? (
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
              <div className="card-desc">Click a field in the lineage graph.</div>
            )
          ) : selectedStage ? (
            <div className="card-desc">
              Guarantees tied to fields in <span className="mono">{stageName}</span>: {stageGuarantees.length}
            </div>
          ) : (
            <div className="card-desc">Select a stage, or switch to Field lineage for blast radius.</div>
          )}
        </div>

        <div className="card">
          <div className="card-title">Guarantees</div>
          <div className="card-desc" style={{ marginBottom: 10 }}>
            From static analysis on load — not hardcoded.
          </div>
          {mode === "lineage" && !selectedNode && (
            <div className="card-desc">Select a field to filter.</div>
          )}
          {mode === "lineage" && selectedNode && relatedGuarantees.length === 0 && (
            <div className="card-desc">No findings for this field.</div>
          )}
          {mode !== "lineage" && !selectedStage && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, maxHeight: 280, overflowY: "auto" }}>
              {guarantees.data!.slice(0, 8).map((g) => (
                <GuaranteeRow key={g.id} g={g} />
              ))}
              {guarantees.data!.length > 8 && (
                <div className="card-desc">Showing 8 of {guarantees.data!.length}. See Guarantees for all.</div>
              )}
            </div>
          )}
          {mode !== "lineage" && selectedStage && stageGuarantees.length === 0 && (
            <div className="card-desc">No findings for fields in this stage.</div>
          )}
          {mode !== "lineage" && selectedStage && stageGuarantees.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, maxHeight: 280, overflowY: "auto" }}>
              {stageGuarantees.map((g) => (
                <GuaranteeRow key={g.id} g={g} />
              ))}
            </div>
          )}
          {mode === "lineage" && relatedGuarantees.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {relatedGuarantees.map((g) => (
                <GuaranteeRow key={g.id} g={g} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
