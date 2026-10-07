import { useMemo, useState } from "react"
import { useGuarantees } from "../api/hooks"
import { ErrorCard, LoadingCard } from "../components/QueryState"
import { StatusPill } from "../components/StatusPill"
import { toneForStatus } from "../components/statusTone"
import type { GuaranteeStatus } from "../api/types"

const FILTERS: Array<GuaranteeStatus | "all"> = ["all", "pending", "confirmed", "rejected"]

export function Guarantees() {
  const guarantees = useGuarantees()
  const [filter, setFilter] = useState<GuaranteeStatus | "all">("all")

  const counts = useMemo(() => {
    const c = { pending: 0, confirmed: 0, rejected: 0 }
    for (const g of guarantees.data ?? []) c[g.status]++
    return c
  }, [guarantees.data])

  if (guarantees.isLoading) return <div className="page"><LoadingCard /></div>
  if (guarantees.isError) return <div className="page"><ErrorCard error={guarantees.error} /></div>

  const rows = (guarantees.data ?? []).filter((g) => filter === "all" || g.status === filter)

  return (
    <div className="page">
      <div className="card-title">What the pipeline silently assumes</div>
      <div className="card-desc">
        Each row comes from static analysis of the code, not from documentation — it only
        counts as a guarantee once a person confirms it.
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className="btn"
            style={
              filter === f
                ? { background: "var(--accent-soft)", borderColor: "var(--accent)", color: "var(--accent-text)" }
                : undefined
            }
          >
            {f === "all" ? `All (${guarantees.data?.length ?? 0})` : `${f} (${counts[f]})`}
          </button>
        ))}
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Kind</th>
              <th>Field</th>
              <th>What the code implies</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((g) => (
              <tr key={g.id}>
                <td><StatusPill tone={toneForStatus(g.status)} label={g.status} /></td>
                <td className="mono">{g.kind}</td>
                <td className="mono">{g.field ?? "—"}</td>
                <td style={{ maxWidth: 420 }}>{g.message}</td>
                <td className="mono" style={{ color: "var(--text-muted)" }}>
                  {g.file}:{g.line}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>
                  No findings in this category.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
