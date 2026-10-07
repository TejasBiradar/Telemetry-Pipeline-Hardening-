import { useEffect, useState } from "react"
import { useHealth, useGuarantees } from "../api/hooks"
import { StatusPill } from "./StatusPill"

interface PipelineInfo {
  active: string
  pipelines: Array<{ id: string; name: string }>
}

export function TopBar({ title }: { title: string }) {
  const health = useHealth()
  const guarantees = useGuarantees()
  const connected = health.data?.status === "ok"
  const confirmedCount = guarantees.data?.filter((g) => g.status === "confirmed").length ?? 0

  const [pipelineInfo, setPipelineInfo] = useState<PipelineInfo | null>(null)

  useEffect(() => {
    fetch("/api/pipelines")
      .then(r => r.json())
      .then(setPipelineInfo)
      .catch(() => {})
  }, [])

  const activePipelineName = pipelineInfo?.pipelines.find(p => p.id === pipelineInfo.active)?.name ?? "Loading..."

  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
          📦 {activePipelineName}
        </div>
      </div>
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
