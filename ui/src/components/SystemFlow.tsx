export function SystemFlow() {
  const steps = [
    {
      num: 1,
      title: "Code Graph",
      desc: "Static analysis of legacy pipeline code",
      icon: "📊",
    },
    {
      num: 2,
      title: "Findings",
      desc: "Reconstructed guarantees & assumptions",
      icon: "🔍",
    },
    {
      num: 3,
      title: "Approvals",
      desc: "Human review & confirmation",
      icon: "✓",
    },
    {
      num: 4,
      title: "Checks",
      desc: "Data quality checks at each checkpoint",
      icon: "🛡️",
    },
    {
      num: 5,
      title: "Evaluation",
      desc: "Measure detection quality (86% recall)",
      icon: "📈",
    },
  ]

  return (
    <div>
      <div style={{ marginTop: 28 }}>
        <div className="card-title">How the System Works</div>
        <div className="card-desc">From understanding the legacy pipeline to protecting it with checks.</div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div style={{ display: "flex", gap: 0, alignItems: "stretch", overflowX: "auto", paddingBottom: 8 }}>
          {steps.map((step, idx) => (
            <div key={step.num} style={{ display: "flex", alignItems: "center", flex: 1, minWidth: 0 }}>
              <div
                style={{
                  flex: 1,
                  padding: "12px",
                  background: "var(--accent-soft)",
                  borderRadius: "var(--radius-md)",
                  textAlign: "center",
                  border: "2px solid var(--accent)",
                }}
              >
                <div style={{ fontSize: 24, marginBottom: 4 }}>{step.icon}</div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--accent-text)" }}>{step.title}</div>
                <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>{step.desc}</div>
              </div>
              {idx < steps.length - 1 && (
                <div style={{ fontSize: 18, margin: "0 8px", color: "var(--accent)" }}>→</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
