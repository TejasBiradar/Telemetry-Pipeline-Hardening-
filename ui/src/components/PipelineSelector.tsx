import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"

export function PipelineSelector({
  onPipelineChange
}: {
  onPipelineChange?: (pipeline: string) => void
}) {
  const [pipelines, setPipelines] = useState<Array<{id: string; name: string}>>([])
  const [active, setActive] = useState("web_analytics")
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  useEffect(() => {
    // Load pipelines from API
    fetch("/api/pipelines")
      .then(r => r.json())
      .then(data => {
        setPipelines(data.pipelines)
        setActive(data.active)
      })
      .catch(() => setPipelines([]))
  }, [])

  const handleChange = async (pipelineId: string) => {
    setLoading(true)
    try {
      const res = await fetch(`/api/pipelines/${pipelineId}/select`, { method: "PUT" })
      if (res.ok) {
        setActive(pipelineId)
        onPipelineChange?.(pipelineId)

        // Invalidate all React Query caches to fetch fresh data for new pipeline
        await queryClient.invalidateQueries()

        // Also do a full reload to be extra sure
        setTimeout(() => {
          console.log(`Switched to pipeline: ${pipelineId}`)
          window.location.reload()
        }, 300)
      }
    } catch (e) {
      console.error("Failed to select pipeline", e)
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: "12px 16px", background: "var(--surface-2)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>ACTIVE PIPELINE</div>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", marginTop: 2 }}>
          📦 {pipelines.find(p => p.id === active)?.name || active}
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <select
          value={active}
          onChange={(e) => handleChange(e.target.value)}
          disabled={loading}
          style={{
            padding: "6px 10px",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            fontSize: 12,
            cursor: loading ? "not-allowed" : "pointer",
            color: "var(--text)",
            opacity: loading ? 0.6 : 1,
          }}
        >
          {pipelines.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        {/* TODO: Implement pipeline upload
        <button
          style={{
            padding: "6px 12px",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            fontSize: 12,
            cursor: "pointer",
            color: "var(--accent-text)",
          }}
        >
          📤 Upload Pipeline
        </button>
        */}
      </div>
    </div>
  )
}
