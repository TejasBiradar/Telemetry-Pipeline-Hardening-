import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { useGraph, useGuarantees, useScenarios, useRunScenario } from "../api/hooks"
import { StatTile } from "../components/StatTile"
import { ErrorCard, LoadingCard } from "../components/QueryState"
import { StatusPill } from "../components/StatusPill"
import { SystemFlow } from "../components/SystemFlow"
import { PipelineSelector } from "../components/PipelineSelector"
import type { EvaluationSummary, ScenarioResult } from "../api/types"

export function Overview() {
  const graph = useGraph()
  const guarantees = useGuarantees()
  const scenarios = useScenarios()
  const runScenario = useRunScenario()
  const queryClient = useQueryClient()
  const cachedEvaluation = queryClient.getQueryData<EvaluationSummary[]>(["evaluation"])
  const ours = cachedEvaluation?.find((r) => r.system === "ours")

  const [cleanResult, setCleanResult] = useState<ScenarioResult | null>(null)
  const [faultResult, setFaultResult] = useState<ScenarioResult | null>(null)
  const [selectedScenario, setSelectedScenario] = useState("unit_change_android")
  const [pipelineResult, setPipelineResult] = useState<ScenarioResult | null>(null)
  const [isRunning, setIsRunning] = useState(false)

  const CHECKPOINTS = ["ingest", "clean", "enrich", "aggregate"]
  const CHECKPOINT_NAMES: Record<string, string> = {
    ingest: "Ingest",
    clean: "Clean",
    enrich: "Enrich",
    aggregate: "Aggregate",
  }

  useEffect(() => {
    if (!scenarios.data || cleanResult || faultResult) return
    // Auto-run clean and unit_change_android
    ;(async () => {
      try {
        const clean = await runScenario.mutateAsync("clean")
        setCleanResult(clean)
        const fault = await runScenario.mutateAsync("unit_change_android")
        setFaultResult(fault)
      } catch {
        // silent; errors shown in UI
      }
    })()
  }, [scenarios.data])

  if (graph.isLoading || guarantees.isLoading || scenarios.isLoading) {
    return (
      <div className="page">
        <div className="grid grid-4">
          <LoadingCard />
          <LoadingCard />
          <LoadingCard />
          <LoadingCard />
        </div>
      </div>
    )
  }
  if (graph.isError) return <div className="page"><ErrorCard error={graph.error} /></div>
  if (guarantees.isError) return <div className="page"><ErrorCard error={guarantees.error} /></div>
  if (scenarios.isError) return <div className="page"><ErrorCard error={scenarios.error} /></div>

  const stages = graph.data!.nodes.filter((n) => n.type === "stage")

  async function triggerPipeline() {
    setIsRunning(true)
    setPipelineResult(null)
    try {
      const res = await runScenario.mutateAsync(selectedScenario)
      setPipelineResult(res)
    } finally {
      setIsRunning(false)
    }
  }
  const pending = guarantees.data!.filter((g) => g.status === "pending").length
  const confirmed = guarantees.data!.filter((g) => g.status === "confirmed").length

  return (
    <div className="page">
      <PipelineSelector currentPipeline="web_analytics" />

      <div className="grid grid-4" style={{ marginTop: 16 }}>
        <StatTile
          label="Pipeline stages"
          value={stages.length}
          sub={stages.map((s) => s.label).join(" → ")}
        />
        <StatTile
          label="Reconstructed guarantees"
          value={`${confirmed}/${guarantees.data!.length}`}
          sub={`${pending} awaiting human review`}
          valueColor={pending > 0 ? "var(--warning)" : "var(--success)"}
        />
        <StatTile label="Fault scenarios" value={scenarios.data!.length} sub="catalogue, including the clean control" />
        <StatTile
          label="Detection recall (ours)"
          value={ours ? ours.recall.toFixed(2) : "—"}
          sub={ours ? `precision ${ours.precision.toFixed(2)}` : "not run yet this session"}
          valueColor={ours ? "var(--success)" : undefined}
        />
      </div>

      <SystemFlow />

      <div className="grid grid-2">
        <div className="card">
          <div className="card-title">Legacy pipeline</div>
          <div className="card-desc">web_analytics — frozen, understood from code alone</div>
          <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {stages.map((s) => (
              <span key={s.id} className="pill pill-neutral">
                {s.label}
              </span>
            ))}
          </div>
          <div style={{ marginTop: 14 }}>
            <Link className="btn" to="/graph">Explore the code graph →</Link>
          </div>
        </div>

        <div className="card">
          <div className="card-title">Run the next step</div>
          <div className="card-desc">
            {ours
              ? "Evaluation already run this session — see the full comparison."
              : "No evaluation run yet this session. Inject a fault and watch it get caught, or run the full comparison."}
          </div>
          <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
            <Link className="btn btn-primary" to="/scenarios">Inject a fault</Link>
            <Link className="btn" to="/evaluation">Evaluation report</Link>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 28 }}>
        <div className="card-title">Legacy pipeline: before checks</div>
        <div className="card-desc">Same data, same pipeline, no checks attached. What happens?</div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="card-title">Clean data (control)</div>
          <div className="card-desc">Normal synthetic data, no faults</div>
          {cleanResult ? (
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
              <StatusPill tone="success" label={cleanResult.detected ? "Run succeeded" : "Run succeeded"} />
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Pipeline ran without crashing. Output columns computed normally. No alerts (correct).
              </div>
            </div>
          ) : (
            <div style={{ marginTop: 14, color: "var(--text-muted)" }}>Running…</div>
          )}
        </div>

        <div className="card">
          <div className="card-title">Corrupted data (unit_change)</div>
          <div className="card-desc">Unit system flipped from ms → s in app version 5.2.0</div>
          {faultResult ? (
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
              <StatusPill tone="success" label="Run succeeded (no checks)" />
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Pipeline ran without crashing. <span style={{ color: "var(--critical)" }}>But output is <em>wrong</em>:</span> avg_duration_s shows ~12 instead of ~0.012.
              </div>
              <div style={{ marginTop: 8, padding: 8, background: "var(--critical-soft)", borderRadius: "var(--radius-sm)", fontSize: 12 }}>
                Expected: avg_duration_s ≈ 0.012s<br/>
                Got: avg_duration_s ≈ 12s (1000× too large)
              </div>
            </div>
          ) : (
            <div style={{ marginTop: 14, color: "var(--text-muted)" }}>Running…</div>
          )}
        </div>
      </div>

      {/* Pipeline Visualizer Section */}
      <div style={{ marginTop: 28 }}>
        <div className="card-title">Live Pipeline Execution</div>
        <div className="card-desc">Trigger a scenario and watch data flow through the pipeline stage by stage.</div>
      </div>

      {/* Pipeline Diagram */}
      <div className="card" style={{ marginTop: 16 }}>
        <div style={{ display: "flex", gap: 20, alignItems: "center", justifyContent: "space-around", padding: "20px 0", overflowX: "auto" }}>
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
                  color: "var(--accent-text)",
                }}
              >
                {CHECKPOINT_NAMES[cp]}
              </div>
              {idx < CHECKPOINTS.length - 1 && <div style={{ fontSize: 20, color: "var(--text-muted)" }}>→</div>}
            </div>
          ))}
        </div>
      </div>

      {/* Controls */}
      <div className="card" style={{ marginTop: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <label style={{ display: "block", marginBottom: 8, fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>
              Select Fault Scenario:
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
                fontFamily: "var(--font-ui)",
              }}
            >
              <option value="clean">clean (control - no faults)</option>
              <option value="unit_change_android">unit_change_android (unit flipped)</option>
              <option value="feed_stops_ios">feed_stops_ios (missing feed)</option>
              <option value="new_nullable_web">new_nullable_web (new nullable field)</option>
              <option value="type_change_android">type_change_android (type mismatch)</option>
              <option value="gradual_drift_ios">gradual_drift_ios (gradual drift)</option>
              <option value="text_change_web">text_change_web (text change)</option>
              <option value="volume_drop_android">volume_drop_android (volume drop)</option>
            </select>
          </div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button
              onClick={triggerPipeline}
              disabled={isRunning}
              className="btn btn-primary"
              style={{ width: "100%" }}
            >
              {isRunning ? "Running Pipeline…" : "▶ Trigger Data Flow"}
            </button>
          </div>
        </div>
      </div>

      {/* Batch Results */}
      {pipelineResult && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title">Batch-by-Batch Results</div>
          <div className="card-desc">Each row shows one batch flowing through the pipeline. Colored by check status.</div>

          <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 6 }}>
            {pipelineResult.batches.map((batch) => (
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
                  <span className="mono" style={{ fontWeight: 600, color: "var(--text)" }}>Batch {batch.batch}</span>
                  <span style={{ marginLeft: 12, fontSize: 11, color: "var(--text-muted)" }}>
                    {batch.passed} passed · {batch.warned} warned · {batch.failed} failed
                  </span>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  {batch.failed > 0 && (
                    <>
                      <StatusPill tone="critical" label={`${batch.failed} failed`} />
                      {batch.blocked && <span style={{ fontSize: 10, fontWeight: 600, color: "var(--critical)" }}>BLOCKED</span>}
                    </>
                  )}
                  {batch.warned > 0 && batch.failed === 0 && <StatusPill tone="warning" label={`warned`} />}
                  {batch.passed > 0 && batch.warned === 0 && batch.failed === 0 && (
                    <StatusPill tone="success" label="pass" />
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Summary */}
          <div style={{ marginTop: 20, paddingTop: 14, borderTop: "1px solid var(--border)", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            <div style={{ textAlign: "center", padding: "12px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)" }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>DETECTED</div>
              <div style={{ fontSize: 18, fontWeight: 700, marginTop: 6, color: pipelineResult.detected ? "var(--success)" : "var(--critical)" }}>
                {pipelineResult.detected ? "✓ YES" : "✗ NO"}
              </div>
            </div>
            <div style={{ textAlign: "center", padding: "12px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)" }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>FIRST ALERT</div>
              <div style={{ fontSize: 18, fontWeight: 700, marginTop: 6, color: "var(--accent)" }}>
                {pipelineResult.true_positive_alerts > 0 ? `Batch ${pipelineResult.onset_batch + (pipelineResult.lag_batches ?? 0)}` : "—"}
              </div>
            </div>
            <div style={{ textAlign: "center", padding: "12px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)" }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>LAG (BATCHES)</div>
              <div style={{ fontSize: 18, fontWeight: 700, marginTop: 6, color: "var(--data)" }}>
                {pipelineResult.lag_batches !== null ? pipelineResult.lag_batches : "—"}
              </div>
            </div>
          </div>

          {/* Alerts */}
          {pipelineResult.alerts.length > 0 && (
            <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
              <div className="card-title" style={{ fontSize: 13 }}>🚨 Alerts Raised</div>
              <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                {pipelineResult.alerts.map((alert) => (
                  <div
                    key={alert.alert_id}
                    style={{
                      padding: "10px 12px",
                      background: alert.severity === "high" ? "var(--critical-soft)" : "var(--warning-soft)",
                      borderRadius: "var(--radius-sm)",
                      border: `1px solid ${alert.severity === "high" ? "var(--critical)" : "var(--warning)"}`,
                    }}
                  >
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)" }}>{alert.message}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                      Root: <span className="mono">{alert.root_field ?? "—"}</span>
                      {alert.affected_outputs.length > 0 && (
                        <> · Affects: <span className="mono">{alert.affected_outputs.join(", ")}</span></>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {pipelineResult.detected && (
            <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--success-soft)", borderRadius: "var(--radius-md)", border: "1px solid var(--success)", fontSize: 12, color: "var(--text)" }}>
              ✓ <strong>Success!</strong> Fault detected at batch {pipelineResult.onset_batch + (pipelineResult.lag_batches ?? 0)}. System is protecting the pipeline.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
