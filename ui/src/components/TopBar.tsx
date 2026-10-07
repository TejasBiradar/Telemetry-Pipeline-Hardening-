import { useHealth } from "../api/hooks"
import { StatusPill } from "./StatusPill"

export function TopBar({ title }: { title: string }) {
  const health = useHealth()
  const connected = health.data?.status === "ok"

  return (
    <header className="topbar">
      <h1>{title}</h1>
      <div className="topbar-right">
        <StatusPill
          tone={connected ? "success" : "critical"}
          label={connected ? "API connected" : health.isLoading ? "Connecting…" : "API unreachable"}
        />
      </div>
    </header>
  )
}
