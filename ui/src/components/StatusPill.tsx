import type { Tone } from "./statusTone"

export function StatusPill({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span className={`pill pill-${tone}`}>
      <span className="dot" />
      {label}
    </span>
  )
}
