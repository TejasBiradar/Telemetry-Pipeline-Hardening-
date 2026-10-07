export function PipelineSelector({ 
  currentPipeline = "web_analytics",
  onPipelineChange 
}: { 
  currentPipeline: string
  onPipelineChange?: (pipeline: string) => void
}) {
  return (
    <div style={{ padding: "12px 16px", background: "var(--surface-2)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>ACTIVE PIPELINE</div>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", marginTop: 2 }}>
          📦 {currentPipeline}
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <select
          value={currentPipeline}
          onChange={(e) => onPipelineChange?.(e.target.value)}
          style={{
            padding: "6px 10px",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            fontSize: 12,
            cursor: "pointer",
            color: "var(--text)",
          }}
        >
          <option value="web_analytics">web_analytics (current)</option>
          <option value="other" disabled>other pipelines (upload below)</option>
        </select>
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
      </div>
    </div>
  )
}
