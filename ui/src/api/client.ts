import type {
  CodeGraph,
  EvaluationSummary,
  Guarantee,
  ScenarioInfo,
  ScenarioResult,
} from "./types"

class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const API_BASE = "/api"

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    const body = await response.text()
    throw new ApiError(response.status, body || `${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

export interface OnboardFinding {
  id: string
  kind: string
  field: string | null
  message: string
  file: string
  line: number
}

export interface CodeOnboardSummary {
  pipeline_id: string
  name: string
  adapter: string
  analyzed_at: string
  findings_count: number
  confirmed_stages: string[]
  has_output_store: boolean
}

export interface AgentCheckpoint {
  name: string
  stage: string
  attach: string
  location: string
  output_uri?: string
}

export interface StageLocation {
  stage: string
  location: string
}

export interface MinioStore {
  type?: string
  endpoint: string
  bucket: string
  prefix?: string
  secure: boolean
  dsn_env?: string
  db_layout?: string
  stage_column?: string
  stages?: StageLocation[]
  layout?: string
}

export interface OutputStoreRequest {
  kind: "minio" | "database"
  endpoint: string
  bucket: string
  prefix: string
  secure: boolean
  dsn_env: string
  db_layout: string
  stage_column: string
  stages: StageLocation[]
}

export interface OnboardGraphNode {
  id: string
  type: string
  label: string
  attrs: Record<string, unknown>
}

export interface OnboardGraphEdge {
  source: string
  target: string
  type: string
}

export interface OnboardGraph {
  nodes: OnboardGraphNode[]
  edges: OnboardGraphEdge[]
}

export interface CodeOnboardDetail {
  pipeline_id: string
  name: string
  source_path: string
  git_url: string
  git_ref: string
  source_subdir: string
  adapter: string
  stages: string[]
  findings: OnboardFinding[]
  findings_count: number
  stage_status: Record<string, string>
  guarantee_status: Record<string, string>
  confirmed_stages: string[]
  agent_checkpoints: AgentCheckpoint[]
  output_store: MinioStore | null
  graph: OnboardGraph
  analyzed_at: string
}

export interface AgentRun {
  pipeline_id: string
  stage: string
  checkpoint: string
  object_key: string
  batch_id: string
  observed_at: string
  results: Array<{
    check?: string
    status?: string
    field?: string | null
    message?: string
  }>
  failed: number
  passed: number
}

export interface CodeOnboardRequest {
  name: string
  source_path?: string
  git_url?: string
  git_ref?: string
  source_subdir?: string
  entry: string
  select: boolean
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  graph: () => request<CodeGraph>("/pipeline/graph"),
  guarantees: () => request<Guarantee[]>("/pipeline/guarantees"),
  setGuaranteeDecision: (id: string, status: string) =>
    request<Guarantee>(`/pipeline/guarantees/${encodeURIComponent(id)}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),
  scenarios: () => request<ScenarioInfo[]>("/scenarios"),
  runScenario: (name: string, system: "none" | "ours" = "ours") =>
    request<ScenarioResult>(
      `/scenarios/${encodeURIComponent(name)}/run?system=${system}`,
      { method: "POST" },
    ),
  evaluation: () => request<EvaluationSummary[]>("/evaluation"),
  refreshEvaluation: () =>
    request<EvaluationSummary[]>("/evaluation/refresh", { method: "POST" }),
  getOnboard: () =>
    request<{
      email: string
      pipeline_id: string
      source_note: string
      smtp_configured: boolean
      email_sent?: string | null
      email_error?: string | null
    }>("/onboard"),
  listCodeOnboard: () => request<CodeOnboardSummary[]>("/pipelines/code-onboard"),
  getCodeOnboard: (pipelineId: string) =>
    request<CodeOnboardDetail>(`/pipelines/${encodeURIComponent(pipelineId)}/code-onboard`),
  createCodeOnboard: (body: CodeOnboardRequest) =>
    request<CodeOnboardDetail>("/pipelines/code-onboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  setStageDecisions: (pipelineId: string, decisions: Record<string, string>) =>
    request<CodeOnboardDetail>(`/pipelines/${encodeURIComponent(pipelineId)}/stages/decisions`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisions }),
    }),
  setOnboardGuarantee: (pipelineId: string, guaranteeId: string, status: string) =>
    request<CodeOnboardDetail>(
      `/pipelines/${encodeURIComponent(pipelineId)}/guarantees/${encodeURIComponent(guaranteeId)}/decision`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      },
    ),
  setOutputStore: (pipelineId: string, body: OutputStoreRequest) =>
    request<CodeOnboardDetail>(`/pipelines/${encodeURIComponent(pipelineId)}/output-store`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  agentResults: (pipelineId: string) =>
    request<AgentRun[]>(`/pipelines/${encodeURIComponent(pipelineId)}/agent/results?limit=30`),
  saveOnboard: (body: { email: string; pipeline_id: string; source_note: string }) =>
    request<{
      email: string
      pipeline_id: string
      source_note: string
      smtp_configured: boolean
      email_sent?: string | null
      email_error?: string | null
    }>("/onboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
}

export { ApiError }
