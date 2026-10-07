import { useState } from "react"
import { useGraph, useRunScenario } from "../api/hooks"
import { ErrorCard, LoadingCard } from "../components/QueryState"
import { StatusPill } from "../components/StatusPill"
import type { ScenarioResult } from "../api/types"

const CHECKPOINTS = ["ingest", "clean", "enrich", "aggregate"]
const CHECKPOINT_NAMES: Record<string, string> = {
  ingest: "Ingest",
  clean: "Clean",
  enrich: "Enrich",
  aggregate: "Aggregate",
}

export function PipelineRun() {
  const graph = useGraph()
  const runScenario = useRunScenario()
  const [selectedScenario, setSelectedScenario] = useState("unit_change_android")
  const [result, setResult] = useState<ScenarioResult | null>(null)
  const [isRunning, setIsRunning] = useState(false)

  if (graph.isLoading) return <div className="page"><LoadingCard /></div>
  if (graph.isError) return <div className="page"><ErrorCard error={graph.error} /></div>

  async function triggerPipeline() {
    setIsRunning(true)
    setResult(null)
    try {
      const res = await runScenario.mutateAsync(selectedScenario)
      setResult(res)
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div className="page">
      <div className="card-title">Pipeline Execution Visualizer</div>
      <div className="card-desc">Trigger a faulty scenario and watch data flow through the pipeline. See where checks catch faults.</div>

      {/* Pipeline Diagram */}
      <div className="card" style={{ marginTop: 16 }}>
        <div style={{ display: "flex", gap: 20, alignItems: "center", justifyContent: "space-around", padding: "20px 0" }}>
          {CHECKPOINTS.map((cp, idx) => (
            <div key={cp} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div
                style={{
                  width: 100,
                  height: 60,
                  border: "2px solid var(--accent)",
                  borderRadius: "var(--radius-md)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 12,
                  fontWeight: 600,
                  textAlign: "center",
                  background: "var(--accent-soft)",
                }}
              >
                {CHECKPOINT_NAMES[cp]}
              </div>
              {idx < CHECKPOINTS.length - 1 && <div style={{ fontSize: 20 }}>→</div>}
            </div>
          ))}
        </div>
      </div>

      {/* Controls */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">Run Configuration</div>
        <div style={{ marginTop: 12 }}>
          <label style={{ display: "block", marginBottom: 8, fontSize: 12, color: "var(--text-muted)" }}>
            Scenario:
          </label>
          <select
            value={selectedScenario}
            onChange={(e) => setSelectedScenario(e.target.value)}
            disabled={isRunning}
            style={{
              width: "100%",
              padding: "8px 12px",
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              color: "var(--text)",
              cursor: isRunning ? "not-allowed" : "pointer",
            }}
          >
            <option value="clean">clean (control - no faults)</option>
            <option value="unit_change_android">unit_change_android (duration unit flipped)</option>
            <option value="feed_stops_ios">feed_stops_ios (feed data missing)</option>
            <option value="new_nullable_web">new_nullable_web (new nullable field)</option>
            <option value="type_change_android">type_change_android (type mismatch)</option>
            <option value="gradual_drift_ios">gradual_drift_ios (gradual drift)</option>
            <option value="text_change_web">text_change_web (text change)</option>
            <option value="volume_drop_android">volume_drop_android (volume drop)</option>
          </select>
        </div>
        <button
          onClick={triggerPipeline}
          disabled={isRunning}
          className="btn btn-primary"
          style={{ marginTop: 14, width: "100%" }}
        >
          {isRunning ? "Running Pipeline…" : "Trigger Data Flow"}
        </button>
      </div>

      {/* Batch Timeline */}
      {result && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title">Batch-by-Batch Results</div>
          <div className="card-desc">Each row is one batch flowing through the pipeline. Colored by check status.</div>

          <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
            {result.batches.map((batch) => (
              <div
                key={batch.batch}
                style={{
                  padding: "10px 12px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border)",
                  background: batch.failed > 0 ? "var(--critical-soft)" : batch.warned > 0 ? "var(--warning-soft)" : "var(--success-soft)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div>
                  <span className="mono" style={{ fontWeight: 600 }}>Batch {batch.batch}</span>
                  <span style={{ marginLeft: 12, fontSize: 11, color: "var(--text-muted)" }}>
                    {batch.passed} passed · {batch.warned} warned · {batch.failed} failed
                  </span>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  {batch.failed > 0 && (
                    <>
                      <StatusPill tone="critical" label={`${batch.failed} failed`} />
                      {batch.failing_checks.length > 0 && (
                        <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
                          {batch.failing_checks.join(", ")}
                        </span>
                      )}
                    </>
                  )}
                  {batch.warned > 0 && batch.failed === 0 && <StatusPill tone="warning" label={`${batch.warned} warned`} />}
                  {batch.passed > 0 && batch.warned === 0 && batch.failed === 0 && (
                    <StatusPill tone="success" label="all pass" />
                  )}
                  {batch.blocked && <span style={{ fontSize: 10, color: "var(--critical)", fontWeight: 600 }}>BLOCKED</span>}
                </div>
              </div>
            ))}
          </div>

          {/* Summary */}
          <div style={{ marginTop: 20, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
            <div className="card-title" style={{ fontSize: 14 }}>Detection Summary</div>
            <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
              <div style={{ textAlign: "center", padding: "10px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)" }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Detected</div>
                <div style={{ fontSize: 20, fontWeight: 600, color: result.detected ? "var(--success)" : "var(--critical)" }}>
                  {result.detected ? "✓ YES" : "✗ NO"}
                </div>
              </div>
              <div style={{ textAlign: "center", padding: "10px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)" }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>First Alert</div>
                <div style={{ fontSize: 20, fontWeight: 600 }}>
                  {result.true_positive_alerts > 0 ? `Batch ${result.onset_batch + (result.lag_batches ?? 0)}` : "—"}
                </div>
              </div>
              <div style={{ textAlign: "center", padding: "10px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)" }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Lag (batches)</div>
                <div style={{ fontSize: 20, fontWeight: 600 }}>
                  {result.lag_batches !== null ? result.lag_batches : "—"}
                </div>
              </div>
            </div>
          </div>

          {/* Alerts */}
          {result.alerts.length > 0 && (
            <div style={{ marginTop: 20, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
              <div className="card-title" style={{ fontSize: 14 }}>Alerts Raised</div>
              <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                {result.alerts.map((alert) => (
                  <div
                    key={alert.alert_id}
                    style={{
                      padding: "10px 12px",
                      background: alert.severity === "high" ? "var(--critical-soft)" : "var(--warning-soft)",
                      borderRadius: "var(--radius-sm)",
                      border: `1px solid ${alert.severity === "high" ? "var(--critical)" : "var(--warning)"}`,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 12, fontWeight: 600 }}>{alert.message}</div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                          Root field: <span className="mono">{alert.root_field ?? "—"}</span>
                          {alert.affected_outputs.length > 0 && (
                            <> · Affects: <span className="mono">{alert.affected_outputs.join(", ")}</span></>
                          )}
                        </div>
                      </div>
                      <StatusPill tone={alert.severity === "high" ? "critical" : "warning"} label={alert.severity} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {result && result.batches.length > 0 && (
        <div style={{ marginTop: 20, padding: 14, background: "var(--success-soft)", borderRadius: "var(--radius-md)", border: "1px solid var(--success)" }}>
          <div style={{ fontSize: 13, color: "var(--text)" }}>
            <strong>✓ Demo Complete:</strong> Scenario ran to completion. 
            {result.detected 
              ? ` The system detected the fault at batch ${result.onset_batch + (result.lag_batches ?? 0)}.`
              : ` The fault was not detected — see Guarantees page to approve findings.`}
          </div>
        </div>
      )}
    </div>
  )
}
