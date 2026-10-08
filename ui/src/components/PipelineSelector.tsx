import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"

export function PipelineSelector({
  onPipelineChange,
}: {
  onPipelineChange?: (pipeline: string) => void
}) {
  const [pipelines, setPipelines] = useState<Array<{ id: string; name: string }>>([])
  const [active, setActive] = useState("")
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  useEffect(() => {
    fetch("/api/pipelines")
      .then((r) => r.json())
      .then((data) => {
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
        await queryClient.invalidateQueries()
        setTimeout(() => {
          window.location.reload()
        }, 300)
      }
    } catch (e) {
      console.error("Failed to select pipeline", e)
      setLoading(false)
    }
  }

  return (
    <div className="pipeline-selector">
      <div>
        <div className="pipeline-selector-label">ACTIVE PIPELINE</div>
        <div className="pipeline-selector-name">
          {pipelines.find((p) => p.id === active)?.name || active || "—"}
        </div>
      </div>
      <label htmlFor="pipeline-select" className="sr-only" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden" }}>
        Select pipeline
      </label>
      <select
        id="pipeline-select"
        className="select"
        value={active}
        onChange={(e) => handleChange(e.target.value)}
        disabled={loading}
      >
        {pipelines.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </div>
  )
}
