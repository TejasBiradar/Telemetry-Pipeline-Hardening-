import { useState } from "react"
import { useRunScenario, useScenarios } from "../api/hooks"
import { ErrorCard, LoadingCard } from "../components/QueryState"
import { StatusPill } from "../components/StatusPill"
import type { ScenarioResult } from "../api/types"

export function FaultInjection() {
  const scenarios = useScenarios()
  const runScenario = useRunScenario()
  const [results, setResults] = useState<Record<string, ScenarioResult>>({})
  const [running, setRunning] = useState<string | null>(null)

  if (scenarios.isLoading) return <div className="page"><LoadingCard /></div>
  if (scenarios.isError) return <div className="page"><ErrorCard error={scenarios.error} /></div>

  async function run(name: string) {
    setRunning(name)
    try {
      const result = await runScenario.mutateAsync(name)
      setResults((prev) => ({ ...prev, [name]: result }))
    } finally {
      setRunning(null)
    }
  }

  return (
    <div className="page">
      <div className="card-title">Inject a fault, watch it get caught</div>
      <div className="card-desc">
        Each run generates fresh synthetic data, deliberately breaks it one way, and runs it
        through the real pipeline with every check attached. Same seed every time, so the
        result is reproducible, not theatre.
      </div>

      <div className="grid grid-2">
        {scenarios.data!.map((scenario) => {
          const result = results[scenario.name]
          const isRunning = running === scenario.name
          return (
            <div key={scenario.name} className="card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                <div>
                  <div className="card-title">{scenario.name}</div>
                  <div className="card-desc mono">{scenario.fault_type}</div>
                </div>
                <button
                  className="btn btn-primary"
                  disabled={isRunning}
                  onClick={() => run(scenario.name)}
                >
                  {isRunning ? "Running…" : result ? "Run again" : "Run"}
                </button>
              </div>

              {isRunning && (
                <div style={{ marginTop: 16 }} className="skeleton" >
                  <div style={{ height: 40 }} />
                </div>
              )}

              {!isRunning && result && (
                <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 10 }}>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <StatusPill
                      tone={result.detected ? "success" : "critical"}
                      label={result.detected ? "Caught" : "Missed"}
                    />
                    {result.lag_batches !== null && (
                      <span className="pill pill-neutral">lag: {result.lag_batches} batch(es)</span>
                    )}
                    {result.crashed_at_batch !== null && (
                      <span className="pill pill-warning">pipeline crashed at batch {result.crashed_at_batch}</span>
                    )}
                  </div>

                  {result.alerts.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {result.alerts.map((alert) => (
                        <div
                          key={alert.alert_id}
                          style={{
                            padding: "10px 12px",
                            borderRadius: "var(--radius-sm)",
                            background: "var(--surface-2)",
                            border: "1px solid var(--border)",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                            <span className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
                              {alert.segment ?? "whole batch"}
                            </span>
                            <StatusPill
                              tone={alert.severity === "high" ? "critical" : "warning"}
                              label={alert.severity}
                            />
                          </div>
                          <p style={{ fontSize: 12.5, marginTop: 6 }}>{alert.message}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  {result.alerts.length === 0 && (
                    <p style={{ fontSize: 12.5, color: "var(--text-muted)" }}>No alerts raised.</p>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
