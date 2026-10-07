import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import type { BatchSummary } from "../api/types"

/** Warnings and failures per batch: passes are the norm, so charting them would bury the signal. */
export function BatchTimeline({ batches, onsetBatch }: { batches: BatchSummary[]; onsetBatch: number }) {
  if (batches.length === 0) return <p className="card-desc">No batches were run.</p>
  return (
    <div role="img" aria-label={`Warnings and failures per batch; fault starts at batch ${onsetBatch}`}>
      <ResponsiveContainer width="100%" height={150}>
        <BarChart data={batches} margin={{ top: 22, right: 8, bottom: 0, left: -20 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="batch" tick={{ fill: "var(--text-muted)", fontSize: 11 }} tickLine={false} />
          <YAxis allowDecimals={false} tick={{ fill: "var(--text-muted)", fontSize: 11 }} tickLine={false} axisLine={false} />
          <Tooltip
            cursor={{ fill: "var(--surface-hover)" }}
            contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border-strong)", borderRadius: 8, fontSize: 12 }}
            labelFormatter={(batch) => `Batch ${batch}`}
          />
          <ReferenceLine
            x={onsetBatch}
            stroke="var(--warning)"
            strokeDasharray="4 3"
            label={{ value: "fault starts", fill: "var(--warning)", fontSize: 10, position: "top" }}
          />
          <Bar dataKey="warned" stackId="s" fill="var(--warning)" name="warned" />
          <Bar dataKey="failed" stackId="s" fill="var(--critical)" name="failed" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
