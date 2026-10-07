import { useHealth, useGuarantees } from "../api/hooks"
import { StatusPill } from "./StatusPill"

export function TopBar({ title }: { title: string }) {
  const health = useHealth()
  const guarantees = useGuarantees()
  const connected = health.data?.status === "ok"
  const confirmedCount = guarantees.data?.filter((g) => g.status === "confirmed").length ?? 0

  return (
    <header className="topbar">
      <h1>{title}</h1>
      <div className="topbar-right" style={{ display: "flex", gap: 12, alignItems: "center" }}>
        {confirmedCount > 0 && (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {confirmedCount} check{confirmedCount !== 1 ? "s" : ""} active
          </span>
        )}
        <StatusPill
          tone={connected ? "success" : "critical"}
          label={connected ? "API connected" : health.isLoading ? "Connecting…" : "API unreachable"}
        />
      </div>
    </header>
  )
}
