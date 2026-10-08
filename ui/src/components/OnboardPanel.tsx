import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "../api/client"

/** Compact onboard form for the account menu in the top bar. */
export function OnboardPanel() {
  const queryClient = useQueryClient()
  const onboard = useQuery({ queryKey: ["onboard"], queryFn: api.getOnboard })
  const pipelines = useQuery({
    queryKey: ["pipelines"],
    queryFn: async () => {
      const res = await fetch("/api/pipelines")
      if (!res.ok) throw new Error(await res.text())
      return (await res.json()) as { active: string; pipelines: { id: string; name: string }[] }
    },
  })

  const [email, setEmail] = useState("")
  const [pipelineId, setPipelineId] = useState("")
  const [sourceNote, setSourceNote] = useState("")

  useEffect(() => {
    if (!onboard.data) return
    setEmail(onboard.data.email)
    setPipelineId(onboard.data.pipeline_id || pipelines.data?.active || "")
    setSourceNote(onboard.data.source_note)
  }, [onboard.data, pipelines.data?.active])

  const save = useMutation({
    mutationFn: () => api.saveOnboard({ email, pipeline_id: pipelineId, source_note: sourceNote }),
    onSuccess: (data) => queryClient.setQueryData(["onboard"], data),
  })

  if (onboard.isLoading || pipelines.isLoading) {
    return <div style={{ padding: 12, fontSize: 13, color: "var(--text-muted)" }}>Loading…</div>
  }
  if (onboard.isError) {
    return <div style={{ padding: 12, fontSize: 13, color: "var(--warning)" }}>Could not load onboard settings.</div>
  }

  return (
    <div className="account-panel">
      <div className="card-title" style={{ fontSize: 14 }}>Onboard a pipeline</div>
      <div className="card-desc" style={{ marginBottom: 12 }}>
        Register source and the email that receives alerts.
      </div>

      <label htmlFor="onboard-pipeline" style={{ display: "block", fontSize: 12, fontWeight: 600 }}>
        Pipeline
      </label>
      <select
        id="onboard-pipeline"
        value={pipelineId}
        onChange={(e) => setPipelineId(e.target.value)}
        style={{ width: "100%", marginTop: 6, marginBottom: 12 }}
      >
        {(pipelines.data?.pipelines ?? []).map((p) => (
          <option key={p.id} value={p.id}>{p.name} ({p.id})</option>
        ))}
      </select>

      <label htmlFor="onboard-source" style={{ display: "block", fontSize: 12, fontWeight: 600 }}>
        Pipeline source (note)
      </label>
      <input
        id="onboard-source"
        value={sourceNote}
        onChange={(e) => setSourceNote(e.target.value)}
        placeholder="e.g. github.com/acme/web-analytics@main"
        style={{ width: "100%", marginTop: 6, marginBottom: 12 }}
      />

      <label htmlFor="onboard-email" style={{ display: "block", fontSize: 12, fontWeight: 600 }}>
        Alert email
      </label>
      <input
        id="onboard-email"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@company.com"
        style={{ width: "100%", marginTop: 6, marginBottom: 12 }}
      />

      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
        SMTP: {onboard.data?.smtp_configured ? "configured — mail will send" : "not configured — add SMTP_* to .env"}
      </div>

      <button
        className="btn btn-primary"
        style={{ width: "100%" }}
        disabled={save.isPending || !email || !pipelineId}
        onClick={() => save.mutate()}
      >
        {save.isPending ? "Saving…" : "Save and send welcome email"}
      </button>

      {save.data?.email_sent && (
        <div style={{ marginTop: 10, fontSize: 12, color: "var(--success)" }}>
          Welcome email sent to {save.data.email}.
        </div>
      )}
      {save.data && !save.data.smtp_configured && (
        <div style={{ marginTop: 10, fontSize: 12, color: "var(--warning)" }}>
          Saved locally; SMTP is not set.
        </div>
      )}
      {save.data?.email_error && (
        <div style={{ marginTop: 10, fontSize: 12, color: "var(--warning)" }}>
          Saved, but send failed: {save.data.email_error}
        </div>
      )}
      {save.isError && (
        <div style={{ marginTop: 10, fontSize: 12, color: "var(--warning)" }}>
          {(save.error as Error).message}
        </div>
      )}
    </div>
  )
}
