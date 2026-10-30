import { Navigate, Route, Routes, useLocation } from "react-router-dom"
import { Sidebar } from "./components/Sidebar"
import { TopBar } from "./components/TopBar"
import { ClientFlow } from "./views/ClientFlow"

const TITLES: Record<string, string> = {
  "/source": "Source",
  "/graph": "Code graph",
  "/stages": "Stages",
  "/guarantees": "Guarantees",
  "/results": "Results",
}

function KeepSearch({ pathname }: { pathname: string }) {
  const location = useLocation()
  return <Navigate to={{ pathname, search: location.search }} replace />
}

export function App() {
  const location = useLocation()
  const title = TITLES[location.pathname] ?? "Driftline"

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="content">
        <TopBar title={title} />
        <Routes>
          <Route path="/" element={<KeepSearch pathname="/source" />} />
          <Route path="/clients" element={<KeepSearch pathname="/source" />} />
          <Route path="/source" element={<ClientFlow />} />
          <Route path="/graph" element={<ClientFlow />} />
          <Route path="/stages" element={<ClientFlow />} />
          <Route path="/guarantees" element={<ClientFlow />} />
          <Route path="/outputs" element={<KeepSearch pathname="/source" />} />
          <Route path="/minio" element={<KeepSearch pathname="/source" />} />
          <Route path="/results" element={<ClientFlow />} />
        </Routes>
      </div>
    </div>
  )
}
