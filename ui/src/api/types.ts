// Mirrors api/schemas.py and teleguard/codegraph/model.py's CodeGraph.to_json(). Kept by
// hand in step with the backend, same as the backend's own api/schemas.py is kept by hand
// in step with teleguard/models.py (CLAUDE.md rule 7: shared contracts change deliberately).

export interface GraphNode {
  id: string
  type: "module" | "function" | "field" | "output" | "external" | "stage"
  label: string
  attrs: Record<string, unknown>
  origin: "static" | "runtime" | "both"
}

export interface GraphEdge {
  source: string
  target: string
  type: "imports" | "calls" | "reads" | "writes" | "derives" | "produces" | "next_stage"
  evidence: { file: string; line: number; snippet: string } | null
  attrs: Record<string, unknown>
  origin: "static" | "runtime" | "both"
}

export interface CodeGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export type GuaranteeStatus = "pending" | "confirmed" | "rejected"

export interface Guarantee {
  id: string
  kind: string
  field: string | null
  message: string
  file: string
  line: number
  status: GuaranteeStatus
}

export interface ScenarioInfo {
  name: string
  fault_type: string
}

export interface AlertOut {
  alert_id: string
  severity: string
  segment: string | null
  root_field: string | null
  message: string
  affected_outputs: string[]
}

export interface ScenarioResult {
  scenario: string
  fault_type: string
  detected: boolean
  lag_batches: number | null
  crashed_at_batch: number | null
  true_positive_alerts: number
  false_positive_alerts: number
  alerts: AlertOut[]
}

export interface EvaluationSummary {
  system: string
  precision: number
  recall: number
  mean_lag_batches: number | null
  detection_matrix: Record<string, boolean>
}
