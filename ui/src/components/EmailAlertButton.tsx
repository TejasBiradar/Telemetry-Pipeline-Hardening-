import type { AlertOut } from "../api/types"

/** Opens the user's mail client with the alert and a link to this UI. Demo notify path. */
export function EmailAlertButton({ alert }: { alert: AlertOut }) {
  const to = import.meta.env.VITE_DEMO_ALERT_EMAIL ?? ""
  const pageUrl = `${window.location.origin}${window.location.pathname}`
  const subject = encodeURIComponent(`[Driftline] ${alert.severity}: ${alert.root_field ?? alert.alert_id}`)
  const body = encodeURIComponent(
    [
      alert.message,
      "",
      `Severity: ${alert.severity}`,
      `Segment: ${alert.segment ?? "whole batch"}`,
      `Field: ${alert.root_field ?? "—"}`,
      `First batch: ${alert.first_batch ?? "—"}`,
      `Alert id: ${alert.alert_id}`,
      "",
      `Open in Driftline: ${pageUrl}`,
    ].join("\n"),
  )
  const href = to
    ? `mailto:${encodeURIComponent(to)}?subject=${subject}&body=${body}`
    : `mailto:?subject=${subject}&body=${body}`

  return (
    <a className="btn" href={href} style={{ fontSize: 12, padding: "4px 8px", marginTop: 8, display: "inline-block" }}>
      Email this alert
    </a>
  )
}
