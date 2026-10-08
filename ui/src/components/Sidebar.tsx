import { useEffect, useState } from "react"
import { NavLink } from "react-router-dom"

const NAV = [
  { to: "/", label: "Overview", section: "Monitor", exact: true },
  { to: "/graph", label: "Code Graph", section: "Comprehension" },
  { to: "/guarantees", label: "Guarantees", section: "Comprehension" },
  { to: "/evaluation", label: "Evaluation Report", section: "Evaluation" },
]

function groupBySection() {
  const sections = new Map<string, typeof NAV>()
  for (const item of NAV) {
    const list = sections.get(item.section) ?? []
    list.push(item)
    sections.set(item.section, list)
  }
  return sections
}

export function Sidebar() {
  const sections = groupBySection()
  const [activeId, setActiveId] = useState("")

  useEffect(() => {
    fetch("/api/pipelines")
      .then((r) => r.json())
      .then((data: { active?: string }) => setActiveId(data.active ?? ""))
      .catch(() => setActiveId(""))
  }, [])

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" width="17" height="17">
            <path
              d="M2 13h4l2-7 4 14 3-9 2 6h5"
              stroke="white"
              strokeWidth={2.2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div>
          <div className="brand-name">Driftline</div>
          <div className="brand-sub">{activeId || "telemetry guard"}</div>
        </div>
      </div>

      {[...sections.entries()].map(([section, items]) => (
        <div key={section}>
          <div className="sidebar-section-label">{section}</div>
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.exact}
              className={({ isActive }) => "sidebar-link" + (isActive ? " active" : "")}
            >
              {item.label}
            </NavLink>
          ))}
        </div>
      ))}
    </aside>
  )
}
