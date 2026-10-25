import { useCallback, useState } from "react"
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  api,
  type AgentRun,
  type CodeOnboardDetail,
  type CodeOnboardRequest,
} from "../api/client"
import { StatusPill } from "../components/StatusPill"
import { toneForStatus } from "../components/statusTone"

type PageId = "source" | "stages" | "guarantees" | "outputs" | "results"

function pageFromPath(pathname: string): PageId {
  if (pathname === "/stages") return "stages"
  if (pathname === "/guarantees") return "guarantees"
  if (pathname === "/minio" || pathname === "/outputs") return "outputs"
  if (pathname === "/results") return "results"
  return "source"
}

export function ClientFlow() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const pipelineId = params.get("id") ?? ""
  const page = pageFromPath(location.pathname)

  const detail = useQuery({
    queryKey: ["code-onboard", pipelineId],
    queryFn: () => api.getCodeOnboard(pipelineId),
    enabled: pipelineId.length > 0,
  })
  const results = useQuery({
    queryKey: ["agent-results", pipelineId],
    queryFn: () => api.agentResults(pipelineId),
    enabled: pipelineId.length > 0 && page === "results",
    refetchInterval: page === "results" ? 5000 : false,
  })

  const refresh = useCallback(
    async (id: string) => {
      await queryClient.invalidateQueries({ queryKey: ["code-onboard-list"] })
      await queryClient.invalidateQueries({ queryKey: ["code-onboard", id] })
    },
    [queryClient],
  )

  return (
    <div className="page">
      <section className="card">
        {page === "source" ? (
          <SourcePanel
            onCreated={(id) => {
              void refresh(id)
              navigate({ pathname: "/stages", search: `?id=${id}` })
            }}
          />
        ) : null}
        {page !== "source" && !pipelineId ? (
          <p className="flow-note">
            Register a pipeline from <Link to="/source">Source</Link> first.
          </p>
        ) : null}
        {page === "stages" && pipelineId ? (
          <StagesPanel
            detail={detail.data}
            loading={detail.isLoading}
            error={detail.error}
            onChanged={() => refresh(pipelineId)}
          />
        ) : null}
        {page === "guarantees" && pipelineId ? (
          <GuaranteesPanel
            detail={detail.data}
            loading={detail.isLoading}
            error={detail.error}
            onChanged={() => refresh(pipelineId)}
          />
        ) : null}
        {page === "outputs" && pipelineId ? (
          <OutputsPanel
            detail={detail.data}
            loading={detail.isLoading}
            error={detail.error}
            onChanged={() => refresh(pipelineId)}
          />
        ) : null}
        {page === "results" && pipelineId ? (
          <ResultsPanel
            runs={results.data}
            loading={results.isLoading}
            error={results.error}
          />
        ) : null}
      </section>
    </div>
  )
}

function SourcePanel({ onCreated }: { onCreated: (id: string) => void }) {
  const [name, setName] = useState("")
  const [mode, setMode] = useState<"local" | "git">("local")
  const [sourcePath, setSourcePath] = useState("")
  const [gitUrl, setGitUrl] = useState("")
  const [gitRef, setGitRef] = useState("HEAD")
  const [subdir, setSubdir] = useState("")
  const [entry, setEntry] = useState("run.run")

  const create = useMutation({
    mutationFn: (body: CodeOnboardRequest) => api.createCodeOnboard(body),
    onSuccess: (data) => onCreated(data.pipeline_id),
  })

  const submit = useCallback(() => {
    const body: CodeOnboardRequest = { name: name.trim(), entry: entry.trim() || "run.run", select: true }
    if (mode === "local") body.source_path = sourcePath.trim()
    else {
      body.git_url = gitUrl.trim()
      body.git_ref = gitRef.trim() || "HEAD"
      body.source_subdir = subdir.trim()
    }
    create.mutate(body)
  }, [create, entry, gitRef, gitUrl, mode, name, sourcePath, subdir])

  return (
    <form
      className="flow-form"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <div>
        <div className="card-title">Register source</div>
        <p className="card-desc">We assign a pipeline id. The repo is analyzed, then only metadata is kept.</p>
      </div>
      <label className="flow-label" htmlFor="pipeline-name">
        Display name
        <input id="pipeline-name" className="flow-input" value={name} onChange={(event) => setName(event.target.value)} required />
      </label>
      <fieldset className="flow-choice" style={{ border: 0, padding: 0 }}>
        <legend className="flow-label">Code location</legend>
        <label htmlFor="mode-local">
          <input id="mode-local" type="radio" name="source-mode" checked={mode === "local"} onChange={() => setMode("local")} />
          {" "}Local folder
        </label>
        <label htmlFor="mode-git">
          <input id="mode-git" type="radio" name="source-mode" checked={mode === "git"} onChange={() => setMode("git")} />
          {" "}Remote repository
        </label>
      </fieldset>
      {mode === "local" ? (
        <label className="flow-label" htmlFor="source-path">
          Folder the API can read
          <input id="source-path" className="flow-input" value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} required placeholder="/path/to/pipeline/src" />
        </label>
      ) : (
        <>
          <label className="flow-label" htmlFor="git-url">
            Git URL
            <input id="git-url" className="flow-input" value={gitUrl} onChange={(event) => setGitUrl(event.target.value)} required placeholder="https://github.com/org/repo.git" />
          </label>
          <label className="flow-label" htmlFor="git-ref">
            Branch or tag
            <input id="git-ref" className="flow-input" value={gitRef} onChange={(event) => setGitRef(event.target.value)} />
          </label>
          <label className="flow-label" htmlFor="source-subdir">
            Subfolder inside the repo
            <input id="source-subdir" className="flow-input" value={subdir} onChange={(event) => setSubdir(event.target.value)} placeholder="src" />
          </label>
        </>
      )}
      <label className="flow-label" htmlFor="entry-point">
        Python entry (module.function)
        <input id="entry-point" className="flow-input" value={entry} onChange={(event) => setEntry(event.target.value)} />
      </label>
      {create.isError ? <p className="flow-error">{errorText(create.error)}</p> : null}
      <div>
        <button type="submit" className="btn btn-primary" disabled={create.isPending || name.trim().length === 0}>
          {create.isPending ? "Analyzing…" : "Analyze and register"}
        </button>
      </div>
    </form>
  )
}

function StagesPanel({
  detail,
  loading,
  error,
  onChanged,
}: {
  detail: CodeOnboardDetail | undefined
  loading: boolean
  error: Error | null
  onChanged: () => Promise<void>
}) {
  const decide = useMutation({
    mutationFn: (decisions: Record<string, string>) => {
      if (!detail) throw new Error("No pipeline loaded")
      return api.setStageDecisions(detail.pipeline_id, decisions)
    },
    onSuccess: () => {
      void onChanged()
    },
  })

  if (loading) return <p className="flow-note">Loading stages…</p>
  if (error) return <p className="flow-error">{errorText(error)}</p>
  if (!detail) return null

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <div className="card-title">Confirm stages</div>
        <p className="card-desc">Only confirmed stages are watched. Folder name under MinIO must match the stage name.</p>
      </div>
      <div className="flow-row">
        <button type="button" className="btn" onClick={() => decide.mutate(mapStages(detail.stages, "confirmed"))} disabled={decide.isPending}>
          Confirm all
        </button>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Stage</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {detail.stages.map((stage) => {
              const status = detail.stage_status[stage] ?? "pending"
              return (
                <tr key={stage}>
                  <td className="mono">{stage}</td>
                  <td><StatusPill tone={toneForStatus(status)} label={status} /></td>
                  <td>
                    <div className="flow-row">
                      <button type="button" className="btn" disabled={decide.isPending || status === "confirmed"} onClick={() => decide.mutate({ [stage]: "confirmed" })}>
                        Confirm
                      </button>
                      <button type="button" className="btn" disabled={decide.isPending || status === "rejected"} onClick={() => decide.mutate({ [stage]: "rejected" })}>
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function GuaranteesPanel({
  detail,
  loading,
  error,
  onChanged,
}: {
  detail: CodeOnboardDetail | undefined
  loading: boolean
  error: Error | null
  onChanged: () => Promise<void>
}) {
  const decide = useMutation({
    mutationFn: (input: { id: string; status: string }) => {
      if (!detail) throw new Error("No pipeline loaded")
      return api.setOnboardGuarantee(detail.pipeline_id, input.id, input.status)
    },
    onSuccess: () => {
      void onChanged()
    },
  })

  if (loading) return <p className="flow-note">Loading guarantees…</p>
  if (error) return <p className="flow-error">{errorText(error)}</p>
  if (!detail) return null

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <div className="card-title">Confirm guarantees</div>
        <p className="card-desc">Confirmed rules become the checks the agent runs on each new file.</p>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Kind</th>
              <th>Field</th>
              <th>Meaning</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {detail.findings.map((finding) => {
              const status = detail.guarantee_status[finding.id] ?? "pending"
              return (
                <tr key={finding.id}>
                  <td><StatusPill tone={toneForStatus(status)} label={status} /></td>
                  <td className="mono">{finding.kind}</td>
                  <td className="mono">{finding.field ?? "—"}</td>
                  <td>{finding.message}</td>
                  <td>
                    <div className="flow-row">
                      <button type="button" className="btn" disabled={decide.isPending || status === "confirmed"} onClick={() => decide.mutate({ id: finding.id, status: "confirmed" })}>
                        Confirm
                      </button>
                      <button type="button" className="btn" disabled={decide.isPending || status === "rejected"} onClick={() => decide.mutate({ id: finding.id, status: "rejected" })}>
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function OutputsPanel({
  detail,
  loading,
  error,
  onChanged,
}: {
  detail: CodeOnboardDetail | undefined
  loading: boolean
  error: Error | null
  onChanged: () => Promise<void>
}) {
  if (loading) return <p className="flow-note">Loading output store…</p>
  if (error) return <p className="flow-error">{errorText(error)}</p>
  if (!detail) return null
  return <OutputForm key={JSON.stringify(detail.output_store ?? null)} detail={detail} onChanged={onChanged} />
}

function OutputForm({
  detail,
  onChanged,
}: {
  detail: CodeOnboardDetail
  onChanged: () => Promise<void>
}) {
  const saved = detail.output_store
  const initialKind = saved?.type === "database" ? "database" : "minio"
  const inferred = inferLayout(saved)
  const [kind, setKind] = useState<"minio" | "database">(initialKind)
  const [layout, setLayout] = useState<FolderLayout>(inferred.layout)
  const [folder, setFolder] = useState(inferred.folder)
  const [endpoint, setEndpoint] = useState(saved?.endpoint || "http://localhost:9000")
  const [bucket, setBucket] = useState(saved?.bucket || "demo")
  const [secure, setSecure] = useState(saved?.secure ?? false)
  const [dsnEnv, setDsnEnv] = useState(saved?.dsn_env || "STAGE_DATABASE_URL")
  const [dbLayout, setDbLayout] = useState<"per_table" | "shared_table">(
    saved?.db_layout === "shared_table" ? "shared_table" : "per_table",
  )
  const [sharedTable, setSharedTable] = useState(saved?.stages?.[0]?.location ?? "")
  const [stageColumn, setStageColumn] = useState(saved?.stage_column || "stage")
  const [tables, setTables] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      detail.confirmed_stages.map((stage) => [
        stage,
        saved?.db_layout === "shared_table"
          ? stage
          : (saved?.stages?.find((item) => item.stage === stage)?.location ?? stage),
      ]),
    ),
  )

  const save = useMutation({
    mutationFn: () =>
      api.setOutputStore(detail.pipeline_id, {
        kind,
        endpoint: endpoint.trim(),
        bucket: bucket.trim(),
        secure,
        dsn_env: dsnEnv.trim() || "STAGE_DATABASE_URL",
        db_layout: kind === "database" ? dbLayout : "",
        stage_column: kind === "database" && dbLayout === "shared_table" ? stageColumn.trim() : "",
        stages: detail.confirmed_stages.map((stage) => ({
          stage,
          location: stageLocation(kind, layout, folder, dbLayout, sharedTable, tables, stage),
        })),
      }),
    onSuccess: () => {
      void onChanged()
    },
  })

  return (
    <form
      className="flow-form"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate()
      }}
    >
      <div>
        <div className="card-title">Where each stage writes</div>
        <p className="card-desc">
          {kind === "minio"
            ? "One folder for the pipeline. Choose whether each stage gets its own subfolder or a file in that same folder."
            : "Driftline does not guess the tables. Tell it whether each stage has its own table, or every stage is a row in one table."}
        </p>
      </div>
      <fieldset className="flow-choice" style={{ border: 0, padding: 0 }}>
        <legend className="flow-label">Store</legend>
        <label htmlFor="store-minio">
          <input
            id="store-minio"
            type="radio"
            name="store-kind"
            checked={kind === "minio"}
            onChange={() => setKind("minio")}
          />
          {" "}MinIO
        </label>
        <label htmlFor="store-database">
          <input
            id="store-database"
            type="radio"
            name="store-kind"
            checked={kind === "database"}
            onChange={() => setKind("database")}
          />
          {" "}Database
        </label>
      </fieldset>
      {kind === "minio" ? (
        <>
          <label className="flow-label" htmlFor="minio-endpoint">
            Endpoint
            <input id="minio-endpoint" className="flow-input" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} required />
          </label>
          <label className="flow-label" htmlFor="minio-bucket">
            Bucket
            <input id="minio-bucket" className="flow-input" value={bucket} onChange={(event) => setBucket(event.target.value)} required />
          </label>
          <label className="flow-choice" htmlFor="minio-secure">
            <input id="minio-secure" type="checkbox" checked={secure} onChange={(event) => setSecure(event.target.checked)} />
            Use HTTPS
          </label>
          <label className="flow-label" htmlFor="output-folder">
            Folder
            <input id="output-folder" className="flow-input" value={folder} onChange={(event) => setFolder(event.target.value)} required />
          </label>
          <fieldset className="flow-choice" style={{ border: 0, padding: 0 }}>
            <legend className="flow-label">Layout</legend>
            <label htmlFor="layout-subfolder">
              <input
                id="layout-subfolder"
                type="radio"
                name="output-layout"
                checked={layout === "subfolder"}
                onChange={() => setLayout("subfolder")}
              />
              {" "}Subfolder
            </label>
            <label htmlFor="layout-single">
              <input
                id="layout-single"
                type="radio"
                name="output-layout"
                checked={layout === "single"}
                onChange={() => setLayout("single")}
              />
              {" "}Single folder
            </label>
          </fieldset>
          <p className="flow-note">
            {layout === "subfolder"
              ? "Each stage is a folder under this path, for example outputs/ingest/."
              : "Every stage file sits in this one folder. The file name starts with the stage, for example outputs/ingest.csv."}
          </p>
        </>
      ) : (
        <>
          <label className="flow-label" htmlFor="dsn-env">
            Env var that holds the database URL
            <input id="dsn-env" className="flow-input" value={dsnEnv} onChange={(event) => setDsnEnv(event.target.value)} required />
          </label>
          <fieldset className="flow-choice" style={{ border: 0, padding: 0 }}>
            <legend className="flow-label">Tables</legend>
            <label htmlFor="db-per-table">
              <input
                id="db-per-table"
                type="radio"
                name="db-layout"
                checked={dbLayout === "per_table"}
                onChange={() => setDbLayout("per_table")}
              />
              {" "}One table per stage
            </label>
            <label htmlFor="db-shared-table">
              <input
                id="db-shared-table"
                type="radio"
                name="db-layout"
                checked={dbLayout === "shared_table"}
                onChange={() => setDbLayout("shared_table")}
              />
              {" "}One table for every stage
            </label>
          </fieldset>
          {dbLayout === "shared_table" ? (
            <>
              <label className="flow-label" htmlFor="shared-table">
                Table
                <input id="shared-table" className="flow-input" value={sharedTable} onChange={(event) => setSharedTable(event.target.value)} required />
              </label>
              <label className="flow-label" htmlFor="stage-column">
                Stage column
                <input id="stage-column" className="flow-input" value={stageColumn} onChange={(event) => setStageColumn(event.target.value)} required />
              </label>
              <p className="flow-note">Rows for a stage are the ones whose stage column equals that stage name.</p>
            </>
          ) : (
            <>
              <p className="flow-note">Type the table that holds each stage. Names can differ from the stage name.</p>
              {detail.confirmed_stages.map((stage) => (
                <label className="flow-label" htmlFor={`table-${stage}`} key={stage}>
                  {stage}
                  <input
                    id={`table-${stage}`}
                    className="flow-input"
                    value={tables[stage] ?? ""}
                    onChange={(event) =>
                      setTables((current) => ({ ...current, [stage]: event.target.value }))
                    }
                    required
                  />
                </label>
              ))}
            </>
          )}
        </>
      )}
      {detail.confirmed_stages.length === 0 ? (
        <p className="flow-note">Confirm at least one stage to declare where it writes.</p>
      ) : null}
      {save.isError ? <p className="flow-error">{errorText(save.error)}</p> : null}
      <div>
        <button type="submit" className="btn btn-primary" disabled={save.isPending || detail.confirmed_stages.length === 0}>
          {save.isPending ? "Saving…" : "Save output locations"}
        </button>
      </div>
      {detail.confirmed_stages.length > 0 ? (
        <ul className="flow-note">
          {detail.confirmed_stages.map((stage) => (
            <li key={stage}>
              <span className="mono">{stage}</span>
              {" → "}
              <span className="mono">
                {kind === "database"
                  ? databasePreview(dbLayout, sharedTable, stageColumn, tables[stage] ?? stage, stage)
                  : previewTarget(kind, bucket, locationFor(kind, layout, folder, stage))}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </form>
  )
}

type FolderLayout = "subfolder" | "single"

function inferLayout(store: CodeOnboardDetail["output_store"]): { layout: FolderLayout; folder: string } {
  const stages = store?.stages ?? []
  if (store?.type === "database") {
    const sample = stages[0]?.location ?? ""
    const dot = sample.lastIndexOf(".")
    return { layout: "subfolder", folder: dot >= 0 ? sample.slice(0, dot) : "" }
  }
  const subfolder = sharedFolder(stages, (stage) => `/${stage}/`)
  if (subfolder !== null) return { layout: "subfolder", folder: subfolder }
  const single = sharedFolder(stages, (stage) => `/${stage}*`)
  if (single !== null) return { layout: "single", folder: single }
  return { layout: "subfolder", folder: (store?.prefix || "demo/outputs").replace(/\/$/, "") }
}

function sharedFolder(
  stages: Array<{ stage: string; location: string }>,
  suffix: (stage: string) => string,
): string | null {
  if (stages.length === 0) return null
  const first = stages[0]
  const end = suffix(first.stage)
  if (!first.location.endsWith(end)) return null
  const folder = first.location.slice(0, -end.length)
  const same = stages.every((item) => item.location === `${folder}${suffix(item.stage)}`)
  return same ? folder : null
}

function locationFor(kind: "minio" | "database", layout: FolderLayout, folder: string, stage: string): string {
  const base = folder.trim().replace(/^\/+|\/+$/g, "")
  if (kind === "database") return stage
  if (!base) return layout === "subfolder" ? `${stage}/` : `${stage}*`
  return layout === "subfolder" ? `${base}/${stage}/` : `${base}/${stage}*`
}

function stageLocation(
  kind: "minio" | "database",
  layout: FolderLayout,
  folder: string,
  dbLayout: "per_table" | "shared_table",
  sharedTable: string,
  tables: Record<string, string>,
  stage: string,
): string {
  if (kind === "database") {
    return dbLayout === "shared_table" ? sharedTable.trim() : (tables[stage] ?? stage).trim()
  }
  return locationFor(kind, layout, folder, stage)
}

function databasePreview(
  dbLayout: "per_table" | "shared_table",
  sharedTable: string,
  stageColumn: string,
  table: string,
  stage: string,
): string {
  if (dbLayout === "shared_table") {
    const name = sharedTable.trim() || "table"
    const column = stageColumn.trim() || "stage"
    return `${name} where ${column} = ${stage}`
  }
  return `table ${table.trim() || stage}`
}

function previewTarget(kind: "minio" | "database", bucket: string, location: string): string {
  const value = location.trim()
  if (!value) return "enter a location"
  if (kind === "database") return `table ${value}`
  return `s3://${bucket.trim() || "bucket"}/${value.replace(/^\//, "")}`
}

function ResultsPanel({
  runs,
  loading,
  error,
}: {
  runs: AgentRun[] | undefined
  loading: boolean
  error: Error | null
}) {
  if (loading) return <p className="flow-note">Loading results…</p>
  if (error) return <p className="flow-error">{errorText(error)}</p>
  const rows = [...(runs ?? [])].reverse()
  if (rows.length === 0) {
    return (
      <p className="flow-note">
        No files checked yet. After stages, guarantees, and MinIO are set, the agent reports here within a few seconds of a new file.
      </p>
    )
  }
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <div className="card-title">Live check results</div>
        <p className="card-desc">Newest first. This list refreshes every 5 seconds.</p>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Stage</th>
              <th>File</th>
              <th>Passed</th>
              <th>Failed</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((run) => (
              <tr key={`${run.observed_at}-${run.object_key}`}>
                <td className="mono">{run.observed_at}</td>
                <td className="mono">{run.stage}</td>
                <td className="mono">{run.object_key}</td>
                <td>{run.passed}</td>
                <td>{run.failed > 0 ? <StatusPill tone="critical" label={String(run.failed)} /> : "0"}</td>
                <td>{failureNotes(run)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function mapStages(stages: string[], status: string): Record<string, string> {
  const decisions: Record<string, string> = {}
  for (const stage of stages) decisions[stage] = status
  return decisions
}

function failureNotes(run: AgentRun): string {
  const notes = run.results
    .filter((result) => result.status === "fail" && result.message)
    .map((result) => result.message)
  return notes.slice(0, 2).join(" · ")
}

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message
  return "Request failed"
}
