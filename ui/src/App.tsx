import { Route, Routes, useLocation } from "react-router-dom"
import { Sidebar } from "./components/Sidebar"
import { TopBar } from "./components/TopBar"
import { Overview } from "./views/Overview"
import { PipelineRun } from "./views/PipelineRun"
import { CodeGraph } from "./views/CodeGraph"
import { Guarantees } from "./views/Guarantees"
import { FaultInjection } from "./views/FaultInjection"
import { Evaluation } from "./views/Evaluation"

const TITLES: Record<string, string> = {
  "/": "Pipeline Overview",
  "/run": "Pipeline Execution",
  "/graph": "Code Graph Explorer",
  "/guarantees": "Reconstructed Guarantees",
  "/scenarios": "Fault Injection",
  "/evaluation": "Evaluation Report",
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
          <Route path="/" element={<Overview />} />
          <Route path="/run" element={<PipelineRun />} />
          <Route path="/graph" element={<CodeGraph />} />
          <Route path="/guarantees" element={<Guarantees />} />
          <Route path="/scenarios" element={<FaultInjection />} />
          <Route path="/evaluation" element={<Evaluation />} />
        </Routes>
      </div>
    </div>
  )
}
