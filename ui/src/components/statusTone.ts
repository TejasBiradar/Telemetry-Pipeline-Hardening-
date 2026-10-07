export type Tone = "success" | "warning" | "critical" | "neutral" | "accent"

/** Maps a guarantee/alert-style status string to a consistent tone across the whole app. */
export function toneForStatus(status: string): Tone {
  switch (status) {
    case "confirmed":
    case "pass":
    case "caught":
      return "success"
    case "pending":
    case "warn":
    case "medium":
      return "warning"
    case "rejected":
    case "fail":
    case "high":
    case "missed":
      return "critical"
    default:
      return "neutral"
  }
}
