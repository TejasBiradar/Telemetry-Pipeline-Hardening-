import { NavLink, useLocation, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { api } from "../api/client"

const NAV = [
  { to: "/source", label: "Source" },
  { to: "/stages", label: "Stages" },
  { to: "/guarantees", label: "Guarantees" },
  { to: "/outputs", label: "Outputs" },
  { to: "/results", label: "Results" },
]

export function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const list = useQuery({
    queryKey: ["code-onboard-list"],
    queryFn: api.listCodeOnboard,
  })
  const pipelineId = new URLSearchParams(location.search).get("id") ?? ""

  function selectPipeline(id: string) {
    const next = new URLSearchParams(location.search)
    if (id) next.set("id", id)
    else next.delete("id")
    const search = next.toString()
    navigate({
      pathname: id ? location.pathname : "/source",
      search: search ? `?${search}` : "",
    })
  }

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
        <div className="sidebar-brand-text">
          <div className="brand-name">Driftline</div>
          <div className="brand-sub">detection</div>
        </div>
      </div>

      <label className="sidebar-picker" htmlFor="pipeline-picker">
        <span className="sidebar-picker-label">Pipeline</span>
        <select
          id="pipeline-picker"
          className="sidebar-select"
          value={pipelineId}
          onChange={(event) => selectPipeline(event.target.value)}
        >
          <option value="">New registration</option>
          {(list.data ?? []).map((item) => (
            <option key={item.pipeline_id} value={item.pipeline_id} title={`${item.name} · ${item.pipeline_id}`}>
              {item.name}
            </option>
          ))}
        </select>
      </label>

      <nav className="sidebar-nav" aria-label="Pipeline setup">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={{ pathname: item.to, search: location.search }}
            className={({ isActive }) => "sidebar-link" + (isActive ? " active" : "")}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
