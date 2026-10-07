import type { ReactNode } from "react"

export function LoadingCard({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="card" aria-busy="true">
      <div className="skeleton" style={{ height: 14, width: "40%", marginBottom: 10 }} />
      <div className="skeleton" style={{ height: 32, width: "60%" }} />
      <span style={{ position: "absolute", left: -9999 }}>{label}</span>
    </div>
  )
}

export function ErrorCard({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong."
  return (
    <div className="error-state">
      Couldn't load this. {message}
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>
}
