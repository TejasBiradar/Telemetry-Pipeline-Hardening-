import { useCallback, useRef, useState, type ChangeEvent, type FormEvent } from "react"
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  api,
  type AgentRun,
  type CodeOnboardDetail,
  type CodeOnboardRequest,
  type OutputStoreRequest,
} from "../api/client"
import { PipelineGraph } from "../components/PipelineGraph"
import { StatusPill } from "../components/StatusPill"
import { toneForStatus } from "../components/statusTone"

type PageId = "source" | "graph" | "stages" | "guarantees" | "results"

function pageFromPath(pathname: string): PageId {
  if (pathname === "/graph") return "graph"
  if (pathname === "/stages") return "stages"
  if (pathname === "/guarantees") return "guarantees"
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
        {page === "source" && pipelineId && detail.isLoading ? (
          <p className="flow-note">Loading pipeline…</p>
        ) : null}
        {page === "source" && pipelineId && detail.error ? (
          <p className="flow-error">{errorText(detail.error)}</p>
        ) : null}
        {page === "source" && (!pipelineId || detail.data) ? (
          <PipelineForm
            key={pipelineId || "new"}
            detail={pipelineId ? detail.data : undefined}
            onCreated={(id) => {
              void refresh(id)
              navigate({ pathname: "/graph", search: `?id=${id}` })
            }}
            onSaved={() => refresh(pipelineId)}
          />
        ) : null}
        {page !== "source" && !pipelineId ? (
          <p className="flow-note">
            Register a pipeline from <Link to="/source">Source</Link> first.
          </p>
        ) : null}
        {page === "graph" && pipelineId ? (
          <GraphPanel detail={detail.data} loading={detail.isLoading} error={detail.error} />
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

function GraphPanel({
  detail,
  loading,
  error,
}: {
  detail: CodeOnboardDetail | undefined
  loading: boolean
  error: Error | null
}) {
  if (loading) return <p className="flow-note">Loading the code graph…</p>
  if (error) return <p className="flow-error">{errorText(error)}</p>
  if (!detail) return null
  return (
    <div className="graph-panel">
      <div>
        <div className="card-title">How this pipeline is built</div>
        <p className="card-desc">
          {detail.name} · {detail.adapter}. Each node is a stage. Select one to see its fields.
        </p>
      </div>
      <PipelineGraph graph={detail.graph} />
    </div>
  )
}

function PipelineForm({
  detail,
  onCreated,
  onSaved,
}: {
  detail: CodeOnboardDetail | undefined
  onCreated: (id: string) => void
  onSaved: () => Promise<void>
}) {
  const advancedRef = useRef<HTMLDetailsElement>(null)
  const [registered, setRegistered] = useState<CodeOnboardDetail | null>(null)
  const record = detail ?? registered ?? undefined
  const locked = record !== undefined
  const [name, setName] = useState(detail?.name ?? "")
  const [mode, setMode] = useState<"local" | "git">(detail?.git_url ? "git" : "local")
  const [sourcePath, setSourcePath] = useState(detail?.source_path ?? "")
  const [gitUrl, setGitUrl] = useState(detail?.git_url ?? "")
  const [gitRef, setGitRef] = useState(detail?.git_ref || "HEAD")
  const [subdir, setSubdir] = useState(detail?.source_subdir ?? "")
  const [entry, setEntry] = useState("run.run")
  const [output, setOutput] = useState<OutputDraft>(() =>
    detail ? outputDraftFromDetail(detail) : emptyOutputDraft(),
  )
  const [outputError, setOutputError] = useState("")
  const stageNames = stageNamesFor(record)

  const save = useMutation({
    mutationFn: async (body: CodeOnboardRequest | null) => {
      if (record) {
        await api.setOutputStore(record.pipeline_id, outputRequest(output, stageNamesFor(record)))
        return record
      }
      if (!body) throw new Error("Registration details are missing")
      const created = await api.createCodeOnboard(body)
      try {
        await api.setOutputStore(created.pipeline_id, outputRequest(output, created.stages))
      } catch (error) {
        setRegistered(created)
        throw error
      }
      return created
    },
    onSuccess: (saved) => {
      if (detail) {
        void onSaved()
        return
      }
      onCreated(saved.pipeline_id)
    },
  })

  const onRegistrationInput = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const { name: field, value } = event.currentTarget
    if (field === "source-mode" && (value === "local" || value === "git")) setMode(value)
    else if (field === "pipeline-name") setName(value)
    else if (field === "source-path") setSourcePath(value)
    else if (field === "git-url") setGitUrl(value)
    else if (field === "git-ref") setGitRef(value)
    else if (field === "source-subdir") setSubdir(value)
    else if (field === "entry-point") setEntry(value)
  }, [])

  const onSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      const message = validateOutput(output, stageNames, locked)
      if (message) {
        setOutputError(message)
        if (advancedRef.current) advancedRef.current.open = true
        return
      }
      setOutputError("")
      const body: CodeOnboardRequest | null = locked
        ? null
        : registrationRequest(name, entry, mode, sourcePath, gitUrl, gitRef, subdir)
      save.mutate(body)
    },
    [entry, gitRef, gitUrl, locked, mode, name, output, save, sourcePath, stageNames, subdir],
  )

  const pendingLabel = detail || registered ? "Saving…" : "Analyzing…"
  const idleLabel = detail || registered ? "Save" : "Analyze and register"

  return (
    <form className="flow-form" onSubmit={onSubmit}>
      <div>
        <div className="card-title">{locked ? "Pipeline registration" : "Register source"}</div>
        <p className="card-desc">
          {locked
            ? "This pipeline is already registered. Output location is under Advanced settings."
            : "We assign a pipeline id. The repo is analyzed, then only metadata is kept. Output location is under Advanced settings."}
        </p>
      </div>
      <label className="flow-label" htmlFor="pipeline-name">
        Display name
        <input
          id="pipeline-name"
          name="pipeline-name"
          className="flow-input"
          value={name}
          onChange={onRegistrationInput}
          readOnly={locked}
          required
        />
      </label>
      <fieldset className="flow-choice" style={{ border: 0, padding: 0 }} disabled={locked}>
        <legend className="flow-label">Code location</legend>
        <label htmlFor="mode-local">
          <input
            id="mode-local"
            type="radio"
            name="source-mode"
            value="local"
            checked={mode === "local"}
            onChange={onRegistrationInput}
          />
          {" "}Local folder
        </label>
        <label htmlFor="mode-git">
          <input
            id="mode-git"
            type="radio"
            name="source-mode"
            value="git"
            checked={mode === "git"}
            onChange={onRegistrationInput}
          />
          {" "}Remote repository
        </label>
      </fieldset>
      {mode === "local" ? (
        <label className="flow-label" htmlFor="source-path">
          Folder the API can read
          <input
            id="source-path"
            name="source-path"
            className="flow-input"
            value={sourcePath}
            onChange={onRegistrationInput}
            readOnly={locked}
            required={!locked}
            placeholder="/path/to/pipeline/src"
          />
        </label>
      ) : (
        <>
          <label className="flow-label" htmlFor="git-url">
            Git URL
            <input
              id="git-url"
              name="git-url"
              className="flow-input"
              value={gitUrl}
              onChange={onRegistrationInput}
              readOnly={locked}
              required={!locked}
              placeholder="https://github.com/org/repo.git"
            />
          </label>
          <label className="flow-label" htmlFor="git-ref">
            Branch or tag
            <input
              id="git-ref"
              name="git-ref"
              className="flow-input"
              value={gitRef}
              onChange={onRegistrationInput}
              readOnly={locked}
            />
          </label>
          <label className="flow-label" htmlFor="source-subdir">
            Subfolder inside the repo
            <input
              id="source-subdir"
              name="source-subdir"
              className="flow-input"
              value={subdir}
              onChange={onRegistrationInput}
              readOnly={locked}
              placeholder="src"
            />
          </label>
        </>
      )}
      {locked ? null : (
        <label className="flow-label" htmlFor="entry-point">
          Python entry (module.function)
          <input
            id="entry-point"
            name="entry-point"
            className="flow-input"
            value={entry}
            onChange={onRegistrationInput}
          />
        </label>
      )}
      <details className="flow-advanced" ref={advancedRef}>
        <summary>
          Advanced settings
          <span className="flow-advanced-hint">Output location</span>
        </summary>
        <OutputSettings draft={output} stageNames={stageNames} onChange={setOutput} />
      </details>
      {outputError ? <p className="flow-error">{outputError}</p> : null}
      {save.isError ? <p className="flow-error">{errorText(save.error)}</p> : null}
      <div>
        <button type="submit" className="btn btn-primary" disabled={save.isPending || name.trim().length === 0}>
          {save.isPending ? pendingLabel : idleLabel}
        </button>
      </div>
    </form>
  )
}

function OutputSettings({
  draft,
  stageNames,
  onChange,
}: {
  draft: OutputDraft
  stageNames: string[]
  onChange: (next: OutputDraft) => void
}) {
  const onInput = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const field = event.currentTarget.name
      const value = event.currentTarget.value
      if (field === "store-kind" && (value === "minio" || value === "database")) {
        onChange({ ...draft, kind: value })
        return
      }
      if (field === "output-layout" && (value === "subfolder" || value === "single")) {
        onChange({ ...draft, layout: value })
        return
      }
      if (field === "db-layout" && (value === "per_table" || value === "shared_table")) {
        onChange({ ...draft, dbLayout: value })
        return
      }
      if (field === "minio-secure") {
        onChange({ ...draft, secure: event.currentTarget.checked })
        return
      }
      if (field.startsWith("table:")) {
        const stage = field.slice("table:".length)
        onChange({ ...draft, tables: { ...draft.tables, [stage]: value } })
        return
      }
      if (field === "endpoint") onChange({ ...draft, endpoint: value })
      else if (field === "bucket") onChange({ ...draft, bucket: value })
      else if (field === "folder") onChange({ ...draft, folder: value })
      else if (field === "dsn-env") onChange({ ...draft, dsnEnv: value })
      else if (field === "shared-table") onChange({ ...draft, sharedTable: value })
      else if (field === "stage-column") onChange({ ...draft, stageColumn: value })
    },
    [draft, onChange],
  )

  return (
    <div className="flow-advanced-body">
      <p className="flow-note">
        {draft.kind === "minio"
          ? "One folder for the pipeline. Choose whether each stage gets its own subfolder or a file in that same folder."
          : "Driftline does not guess the tables. Tell it whether each stage has its own table, or every stage is a row in one table."}
      </p>
      <fieldset className="flow-choice" style={{ border: 0, padding: 0 }}>
        <legend className="flow-label">Store</legend>
        <label htmlFor="store-minio">
          <input
            id="store-minio"
            type="radio"
            name="store-kind"
            value="minio"
            checked={draft.kind === "minio"}
            onChange={onInput}
          />
          {" "}MinIO
        </label>
        <label htmlFor="store-database">
          <input
            id="store-database"
            type="radio"
            name="store-kind"
            value="database"
            checked={draft.kind === "database"}
            onChange={onInput}
          />
          {" "}Database
        </label>
      </fieldset>
      {draft.kind === "minio" ? (
        <>
          <label className="flow-label" htmlFor="minio-endpoint">
            Endpoint
            <input id="minio-endpoint" name="endpoint" className="flow-input" value={draft.endpoint} onChange={onInput} />
          </label>
          <label className="flow-label" htmlFor="minio-bucket">
            Bucket
            <input id="minio-bucket" name="bucket" className="flow-input" value={draft.bucket} onChange={onInput} />
          </label>
          <label className="flow-choice" htmlFor="minio-secure">
            <input
              id="minio-secure"
              name="minio-secure"
              type="checkbox"
              checked={draft.secure}
              onChange={onInput}
            />
            Use HTTPS
          </label>
          <label className="flow-label" htmlFor="output-folder">
            Folder
            <input id="output-folder" name="folder" className="flow-input" value={draft.folder} onChange={onInput} />
          </label>
          <fieldset className="flow-choice" style={{ border: 0, padding: 0 }}>
            <legend className="flow-label">Layout</legend>
            <label htmlFor="layout-subfolder">
              <input
                id="layout-subfolder"
                type="radio"
                name="output-layout"
                value="subfolder"
                checked={draft.layout === "subfolder"}
                onChange={onInput}
              />
              {" "}Subfolder
            </label>
            <label htmlFor="layout-single">
              <input
                id="layout-single"
                type="radio"
                name="output-layout"
                value="single"
                checked={draft.layout === "single"}
                onChange={onInput}
              />
              {" "}Single folder
            </label>
          </fieldset>
          <p className="flow-note">
            {draft.layout === "subfolder"
              ? "Each stage is a folder under this path, for example outputs/ingest/."
              : "Every stage file sits in this one folder. The file name starts with the stage, for example outputs/ingest.csv."}
          </p>
        </>
      ) : (
        <>
          <label className="flow-label" htmlFor="dsn-env">
            Env var that holds the database URL
            <input id="dsn-env" name="dsn-env" className="flow-input" value={draft.dsnEnv} onChange={onInput} />
          </label>
          <fieldset className="flow-choice" style={{ border: 0, padding: 0 }}>
            <legend className="flow-label">Tables</legend>
            <label htmlFor="db-per-table">
              <input
                id="db-per-table"
                type="radio"
                name="db-layout"
                value="per_table"
                checked={draft.dbLayout === "per_table"}
                onChange={onInput}
              />
              {" "}One table per stage
            </label>
            <label htmlFor="db-shared-table">
              <input
                id="db-shared-table"
                type="radio"
                name="db-layout"
                value="shared_table"
                checked={draft.dbLayout === "shared_table"}
                onChange={onInput}
              />
              {" "}One table for every stage
            </label>
          </fieldset>
          {draft.dbLayout === "shared_table" ? (
            <>
              <label className="flow-label" htmlFor="shared-table">
                Table
                <input id="shared-table" name="shared-table" className="flow-input" value={draft.sharedTable} onChange={onInput} />
              </label>
              <label className="flow-label" htmlFor="stage-column">
                Stage column
                <input id="stage-column" name="stage-column" className="flow-input" value={draft.stageColumn} onChange={onInput} />
              </label>
              <p className="flow-note">Rows for a stage are the ones whose stage column equals that stage name.</p>
            </>
          ) : stageNames.length > 0 ? (
            <>
              <p className="flow-note">Type the table that holds each stage. Names can differ from the stage name.</p>
              {stageNames.map((stage) => (
                <StageTableField
                  key={stage}
                  stage={stage}
                  value={draft.tables[stage] ?? stage}
                  onInput={onInput}
                />
              ))}
            </>
          ) : (
            <p className="flow-note">Each stage table uses the stage name. Rename the tables here after the pipeline is registered.</p>
          )}
        </>
      )}
      {stageNames.length > 0 ? (
        <ul className="flow-note">
          {stageNames.map((stage) => (
            <li key={stage}>
              <span className="mono">{stage}</span>
              {" → "}
              <span className="mono">
                {draft.kind === "database"
                  ? databasePreview(draft.dbLayout, draft.sharedTable, draft.stageColumn, draft.tables[stage] ?? stage, stage)
                  : previewTarget(draft.kind, draft.bucket, locationFor(draft.kind, draft.layout, draft.folder, stage))}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="flow-note">Stage locations are filled in when analysis finishes.</p>
      )}
    </div>
  )
}

function StageTableField({
  stage,
  value,
  onInput,
}: {
  stage: string
  value: string
  onInput: (event: ChangeEvent<HTMLInputElement>) => void
}) {
  return (
    <label className="flow-label" htmlFor={`table-${stage}`}>
      {stage}
      <input
        id={`table-${stage}`}
        name={`table:${stage}`}
        className="flow-input"
        value={value}
        onChange={onInput}
      />
    </label>
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

type StoreKind = "minio" | "database"
type DbLayout = "per_table" | "shared_table"
type FolderLayout = "subfolder" | "single"

interface OutputDraft {
  kind: StoreKind
  layout: FolderLayout
  folder: string
  endpoint: string
  bucket: string
  secure: boolean
  dsnEnv: string
  dbLayout: DbLayout
  sharedTable: string
  stageColumn: string
  tables: Record<string, string>
}

function emptyOutputDraft(): OutputDraft {
  return {
    kind: "minio",
    layout: "subfolder",
    folder: "demo/outputs",
    endpoint: "http://localhost:9000",
    bucket: "demo",
    secure: false,
    dsnEnv: "STAGE_DATABASE_URL",
    dbLayout: "per_table",
    sharedTable: "",
    stageColumn: "stage",
    tables: {},
  }
}

function outputDraftFromDetail(detail: CodeOnboardDetail): OutputDraft {
  const saved = detail.output_store
  const inferred = inferLayout(saved)
  const names = stageNamesFor(detail)
  const dbLayout = saved?.db_layout === "shared_table" ? "shared_table" : "per_table"
  return {
    kind: saved?.type === "database" ? "database" : "minio",
    layout: inferred.layout,
    folder: inferred.folder,
    endpoint: saved?.endpoint || "http://localhost:9000",
    bucket: saved?.bucket || "demo",
    secure: saved?.secure ?? false,
    dsnEnv: saved?.dsn_env || "STAGE_DATABASE_URL",
    dbLayout,
    sharedTable: dbLayout === "shared_table" ? (saved?.stages?.[0]?.location ?? "") : "",
    stageColumn: saved?.stage_column || "stage",
    tables: Object.fromEntries(
      names.map((stage) => [
        stage,
        dbLayout === "shared_table"
          ? stage
          : (saved?.stages?.find((item) => item.stage === stage)?.location ?? stage),
      ]),
    ),
  }
}

function stageNamesFor(detail: CodeOnboardDetail | undefined): string[] {
  if (!detail) return []
  return detail.confirmed_stages.length > 0 ? detail.confirmed_stages : detail.stages
}

function registrationRequest(
  name: string,
  entry: string,
  mode: "local" | "git",
  sourcePath: string,
  gitUrl: string,
  gitRef: string,
  subdir: string,
): CodeOnboardRequest {
  const body: CodeOnboardRequest = {
    name: name.trim(),
    entry: entry.trim() || "run.run",
    select: true,
  }
  if (mode === "local") body.source_path = sourcePath.trim()
  else {
    body.git_url = gitUrl.trim()
    body.git_ref = gitRef.trim() || "HEAD"
    body.source_subdir = subdir.trim()
  }
  return body
}

function outputRequest(draft: OutputDraft, stages: string[]): OutputStoreRequest {
  return {
    kind: draft.kind,
    endpoint: draft.endpoint.trim(),
    bucket: draft.bucket.trim(),
    prefix: draft.kind === "minio" ? draft.folder.trim().replace(/^\/+|\/+$/g, "") : "",
    secure: draft.secure,
    dsn_env: draft.dsnEnv.trim() || "STAGE_DATABASE_URL",
    db_layout: draft.kind === "database" ? draft.dbLayout : "",
    stage_column: draft.kind === "database" && draft.dbLayout === "shared_table" ? draft.stageColumn.trim() : "",
    stages: stages.map((stage) => ({
      stage,
      location: stageLocation(draft.kind, draft.layout, draft.folder, draft.dbLayout, draft.sharedTable, draft.tables, stage),
    })),
  }
}

function validateOutput(draft: OutputDraft, stageNames: string[], editing: boolean): string {
  if (draft.kind === "minio") {
    if (!draft.endpoint.trim()) return "Endpoint is required."
    if (!draft.bucket.trim()) return "Bucket is required."
    if (!draft.folder.trim()) return "Folder is required."
    return ""
  }
  if (!draft.dsnEnv.trim()) return "Database URL env var is required."
  if (draft.dbLayout === "shared_table") {
    if (!draft.sharedTable.trim()) return "Table is required."
    if (!draft.stageColumn.trim()) return "Stage column is required."
    return ""
  }
  if (!editing) return ""
  for (const stage of stageNames) {
    if (!(draft.tables[stage] ?? stage).trim()) return `Table for ${stage} is required.`
  }
  return ""
}

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
        No files checked yet. After stages, guarantees, and output locations are set, the agent reports here within a few seconds of a new file.
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
