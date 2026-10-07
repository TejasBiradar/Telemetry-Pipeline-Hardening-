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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const body = await response.text()
    throw new ApiError(response.status, body || `${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  graph: () => request<CodeGraph>("/pipeline/graph"),
  guarantees: () => request<Guarantee[]>("/pipeline/guarantees"),
  scenarios: () => request<ScenarioInfo[]>("/scenarios"),
  runScenario: (name: string) =>
    request<ScenarioResult>(`/scenarios/${encodeURIComponent(name)}/run`, { method: "POST" }),
  evaluation: () => request<EvaluationSummary[]>("/evaluation"),
  refreshEvaluation: () =>
    request<EvaluationSummary[]>("/evaluation/refresh", { method: "POST" }),
}

export { ApiError }
