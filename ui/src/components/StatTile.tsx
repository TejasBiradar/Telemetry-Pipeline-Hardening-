import type { ReactNode } from "react"

export function StatTile({
  label,
  value,
  sub,
  valueColor,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  valueColor?: string
}) {
  return (
    <div className="card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={valueColor ? { color: valueColor } : undefined}>
        {value}
      </div>
      {sub !== undefined && <div className="stat-sub">{sub}</div>}
    </div>
  )
}
