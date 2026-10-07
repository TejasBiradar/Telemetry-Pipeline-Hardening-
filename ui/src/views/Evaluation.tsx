import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { useEvaluation, useRefreshEvaluation, useScenarios } from "../api/hooks"
import { ErrorCard } from "../components/QueryState"
import { StatusPill } from "../components/StatusPill"
import type { EvaluationSummary } from "../api/types"

const SYSTEM_LABEL: Record<string, string> = {
  B0: "B0 — no checks",
  B1: "B1 — naive schema-only",
  ours: "Ours",
}

// A clean control has nothing to catch: staying silent is the right answer, an alert is a false positive.
function DetectionCell({ detected, isControl }: { detected: boolean; isControl: boolean }) {
  if (isControl) {
    return detected
      ? <StatusPill tone="critical" label="false alarm" />
      : <StatusPill tone="success" label="no alert" />
  }
  return <StatusPill tone={detected ? "success" : "neutral"} label={detected ? "caught" : "missed"} />
}

function chartData(reports: EvaluationSummary[]) {
  return reports.map((r) => ({ system: r.system, precision: r.precision, recall: r.recall }))
}

export function Evaluation() {
  const evaluation = useEvaluation()
  const refresh = useRefreshEvaluation()
  const scenarios = useScenarios()
  const controls = new Set((scenarios.data ?? []).filter((s) => s.fault_type === "clean").map((s) => s.name))

  const isComputing = evaluation.isLoading || refresh.isPending

  if (evaluation.isError) return <div className="page"><ErrorCard error={evaluation.error} /></div>

  const reports = refresh.data ?? evaluation.data
  const ours = reports?.find((r) => r.system === "ours")
  const scenarioNames = ours ? Object.keys(ours.detection_matrix) : []

  return (
    <div className="page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div className="card-title">Evaluation report</div>
          <div className="card-desc">
            Precision, recall and lag vs. two baselines — this is the evidence table, not a claim.
          </div>
        </div>
        <button className="btn" disabled={isComputing} onClick={() => refresh.mutate()}>
          {isComputing ? "Running the full suite…" : "Re-run full evaluation"}
        </button>
      </div>

      {isComputing && !reports && (
        <div className="card">
          <div className="card-desc">
            Running 8 scenarios against 3 systems at realistic batch volume — about 100 seconds
            the first time. Not a hang.
          </div>
          <div className="skeleton" style={{ height: 120, marginTop: 14 }} />
        </div>
      )}

      {reports && (
        <>
          <div className="card">
            <div className="card-title">Precision and recall by system</div>
            <div role="img" aria-label="Precision and recall for each system, from 0 to 1" style={{ marginTop: 10 }}>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData(reports)} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="system" tick={{ fill: "var(--text-muted)", fontSize: 12 }} tickLine={false} />
                  <YAxis domain={[0, 1]} tick={{ fill: "var(--text-muted)", fontSize: 11 }} tickLine={false} axisLine={false} />
                  <Tooltip
                    cursor={{ fill: "var(--surface-hover)" }}
                    contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border-strong)", borderRadius: 8, fontSize: 12 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="precision" fill="var(--accent)" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="recall" fill="var(--data)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>System</th>
                  <th>Precision</th>
                  <th>Recall</th>
                  <th>Mean lag (batches)</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.system}>
                    <td style={{ fontWeight: r.system === "ours" ? 700 : 500 }}>
                      {SYSTEM_LABEL[r.system] ?? r.system}
                    </td>
                    <td className="mono">{r.precision.toFixed(2)}</td>
                    <td className="mono">{r.recall.toFixed(2)}</td>
                    <td className="mono">
                      {r.mean_lag_batches !== null ? r.mean_lag_batches.toFixed(1) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card-title" style={{ marginTop: 6 }}>Detection matrix</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Scenario</th>
                  {reports.map((r) => (
                    <th key={r.system}>{r.system}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {scenarioNames.map((name) => (
                  <tr key={name}>
                    <td className="mono">{name}</td>
                    {reports.map((r) => (
                      <td key={r.system}>
                        <DetectionCell detected={r.detection_matrix[name]} isControl={controls.has(name)} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
