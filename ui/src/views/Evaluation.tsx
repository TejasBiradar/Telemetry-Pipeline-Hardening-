import { useEvaluation, useRefreshEvaluation } from "../api/hooks"
import { ErrorCard } from "../components/QueryState"
import { StatusPill } from "../components/StatusPill"

const SYSTEM_LABEL: Record<string, string> = {
  B0: "B0 — no checks",
  B1: "B1 — naive schema-only",
  ours: "Ours",
}

export function Evaluation() {
  const evaluation = useEvaluation()
  const refresh = useRefreshEvaluation()

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
                        <StatusPill
                          tone={r.detection_matrix[name] ? "success" : "neutral"}
                          label={r.detection_matrix[name] ? "caught" : "missed"}
                        />
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
