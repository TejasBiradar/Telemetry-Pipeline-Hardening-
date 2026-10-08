import { useEffect, useRef, useState } from "react"
import { useHealth, useGuarantees } from "../api/hooks"
import { StatusPill } from "./StatusPill"
import { OnboardPanel } from "./OnboardPanel"

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
  const [accountOpen, setAccountOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch("/api/pipelines")
      .then((r) => r.json())
      .then(setPipelineInfo)
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!accountOpen) return
    function onPointerDown(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setAccountOpen(false)
      }
    }
    document.addEventListener("mousedown", onPointerDown)
    return () => document.removeEventListener("mousedown", onPointerDown)
  }, [accountOpen])

  const activePipelineName =
    pipelineInfo?.pipelines.find((p) => p.id === pipelineInfo.active)?.name ?? "…"

  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        <div className="topbar-pipeline">{activePipelineName}</div>
      </div>
      <div className="topbar-right">
        {confirmedCount > 0 && (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {confirmedCount} check{confirmedCount !== 1 ? "s" : ""} active
          </span>
        )}
        <StatusPill
          tone={connected ? "success" : "critical"}
          label={connected ? "API connected" : health.isLoading ? "Connecting…" : "API unreachable"}
        />
        <div className="account-menu" ref={menuRef}>
          <button
            type="button"
            className="account-btn"
            aria-label="Account and onboard"
            aria-expanded={accountOpen}
            onClick={() => setAccountOpen((open) => !open)}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <circle cx="12" cy="8" r="3.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
              <path
                d="M5 19c1.5-3.5 4-5 7-5s5.5 1.5 7 5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
            </svg>
          </button>
          {accountOpen && (
            <div className="account-dropdown" role="dialog" aria-label="Onboard">
              <OnboardPanel />
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
