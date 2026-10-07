import { Link } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { useGraph, useGuarantees, useScenarios } from "../api/hooks"
import { StatTile } from "../components/StatTile"
import { ErrorCard, LoadingCard } from "../components/QueryState"
import type { EvaluationSummary } from "../api/types"

export function Overview() {
  const graph = useGraph()
  const guarantees = useGuarantees()
  const scenarios = useScenarios()
  const queryClient = useQueryClient()
  const cachedEvaluation = queryClient.getQueryData<EvaluationSummary[]>(["evaluation"])
  const ours = cachedEvaluation?.find((r) => r.system === "ours")

  if (graph.isLoading || guarantees.isLoading || scenarios.isLoading) {
    return (
      <div className="page">
        <div className="grid grid-4">
          <LoadingCard />
          <LoadingCard />
          <LoadingCard />
          <LoadingCard />
        </div>
      </div>
    )
  }
  if (graph.isError) return <div className="page"><ErrorCard error={graph.error} /></div>
  if (guarantees.isError) return <div className="page"><ErrorCard error={guarantees.error} /></div>
  if (scenarios.isError) return <div className="page"><ErrorCard error={scenarios.error} /></div>

  const stages = graph.data!.nodes.filter((n) => n.type === "stage")
  const pending = guarantees.data!.filter((g) => g.status === "pending").length
  const confirmed = guarantees.data!.filter((g) => g.status === "confirmed").length

  return (
    <div className="page">
      <div className="grid grid-4">
        <StatTile
          label="Pipeline stages"
          value={stages.length}
          sub={stages.map((s) => s.label).join(" → ")}
        />
        <StatTile
          label="Reconstructed guarantees"
          value={`${confirmed}/${guarantees.data!.length}`}
          sub={`${pending} awaiting human review`}
          valueColor={pending > 0 ? "var(--warning)" : "var(--success)"}
        />
        <StatTile label="Fault scenarios" value={scenarios.data!.length} sub="catalogue, including the clean control" />
        <StatTile
          label="Detection recall (ours)"
          value={ours ? ours.recall.toFixed(2) : "—"}
          sub={ours ? `precision ${ours.precision.toFixed(2)}` : "not run yet this session"}
          valueColor={ours ? "var(--success)" : undefined}
        />
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="card-title">Legacy pipeline</div>
          <div className="card-desc">web_analytics — frozen, understood from code alone</div>
          <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {stages.map((s) => (
              <span key={s.id} className="pill pill-neutral">
                {s.label}
              </span>
            ))}
          </div>
          <div style={{ marginTop: 14 }}>
            <Link className="btn" to="/graph">Explore the code graph →</Link>
          </div>
        </div>

        <div className="card">
          <div className="card-title">Run the next step</div>
          <div className="card-desc">
            {ours
              ? "Evaluation already run this session — see the full comparison."
              : "No evaluation run yet this session. Inject a fault and watch it get caught, or run the full comparison."}
          </div>
          <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
            <Link className="btn btn-primary" to="/scenarios">Inject a fault</Link>
            <Link className="btn" to="/evaluation">Evaluation report</Link>
          </div>
        </div>
      </div>
    </div>
  )
}
