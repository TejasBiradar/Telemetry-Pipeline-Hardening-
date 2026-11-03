import { useCallback, useState, type ChangeEvent, type FormEvent } from "react"
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  api,
  type AgentRun,
  type CodeOnboardDetail,
  type CodeOnboardRequest,
  type MinioStore,
  type OutputStoreRequest,
} from "../api/client"
import { ConfirmDialog } from "../components/ConfirmDialog"
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
            navigate({ pathname: "/source", search: `?id=${id}`, hash: "connector" })
          }}
          onSaved={() => refresh(pipelineId)}
          onDeleted={async () => {
            await queryClient.invalidateQueries({ queryKey: ["code-onboard-list"] })
            await queryClient.removeQueries({ queryKey: ["code-onboard", pipelineId] })
            navigate({ pathname: "/source" })
          }}
        />
      ) : null}
      {page === "source" ? null : (
      <section className="card">
        {!pipelineId ? (
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
            confirmedStages={detail.data?.confirmed_stages ?? []}
            loading={results.isLoading}
            error={results.error}
          />
        ) : null}
      </section>
      )}
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
          {detail.name}. Stages and fields are from this registration&apos;s analysis — not a fixed demo graph.
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
  onDeleted,
}: {
  detail: CodeOnboardDetail | undefined
  onCreated: (id: string) => void
  onSaved: () => Promise<void>
  onDeleted: () => Promise<void>
}) {
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
  const [editingRegistration, setEditingRegistration] = useState(() => !detail)
  const [editingConnector, setEditingConnector] = useState(() => !detail?.output_store)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const stageNames = stageNamesFor(record)
  const connectorSaved = Boolean(record?.output_store)
  const showRegistrationSummary = locked && !editingRegistration
  const showConnectorSummary = locked && connectorSaved && !editingConnector && Boolean(record?.output_store)

  const register = useMutation({
    mutationFn: async (body: CodeOnboardRequest) => {
      if (record?.pipeline_id) {
        return api.updateCodeOnboard(record.pipeline_id, body)
      }
      return api.createCodeOnboard(body)
    },
    onSuccess: async (saved) => {
      setRegistered(saved)
      setEditingRegistration(false)
      // Keep the connector summary closed when the store was preserved on re-analyze.
      setEditingConnector(!saved.output_store)
      if (saved.output_store) {
        setOutput(outputDraftFromDetail(saved))
      }
      if (record?.pipeline_id && record.pipeline_id === saved.pipeline_id) {
        await onSaved()
      } else {
        onCreated(saved.pipeline_id)
      }
    },
  })

  const remove = useMutation({
    mutationFn: async () => {
      if (!record) throw new Error("No pipeline loaded")
      await api.deleteCodeOnboard(record.pipeline_id)
    },
    onSuccess: () => {
      void onDeleted()
    },
  })

  const saveConnector = useMutation({
    mutationFn: async () => {
      if (!record) throw new Error("Register the pipeline first")
      await api.setOutputStore(record.pipeline_id, outputRequest(output, stageNamesFor(record)))
    },
    onSuccess: async () => {
      await onSaved()
      setEditingConnector(false)
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

  const preventSubmit = useCallback((event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
  }, [])

  const onRegister = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      register.mutate(registrationRequest(name, entry, mode, sourcePath, gitUrl, gitRef, subdir))
    },
    [entry, gitRef, gitUrl, mode, name, register, sourcePath, subdir],
  )

  const onSaveConnector = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      const message = validateOutput(output, stageNames, true)
      if (message) {
        setOutputError(message)
        return
      }
      setOutputError("")
      saveConnector.mutate()
    },
    [output, saveConnector, stageNames],
  )

  const sourceLabel = mode === "git"
    ? [gitUrl, subdir].filter((part) => part.trim().length > 0).join(" / ")
    : sourcePath

  return (
    <div className="flow-stack">
    <form className="card flow-form" onSubmit={showRegistrationSummary ? preventSubmit : onRegister}>
      <header className="flow-section-head">
        <div>
          <p className="flow-step">1 · Pipeline</p>
          <div className="card-title">Registration</div>
          <p className="card-desc">
            {showRegistrationSummary
              ? "The source is analyzed. Stages and guarantees come from this registration."
              : "Name the pipeline and point at its code. Analysis keeps the metadata and drops the clone."}
          </p>
        </div>
      </header>
      {showRegistrationSummary ? (
        <>
          <dl className="flow-facts">
            <div>
              <dt>Name</dt>
              <dd>{name}</dd>
            </div>
            <div>
              <dt>{mode === "git" ? "Repository" : "Folder"}</dt>
              <dd className="mono">{sourceLabel || "—"}</dd>
            </div>
            {mode === "git" ? (
              <div>
                <dt>Branch</dt>
                <dd className="mono">{gitRef || "HEAD"}</dd>
              </div>
            ) : null}
            <div>
              <dt>Pipeline id</dt>
              <dd className="mono">{record?.pipeline_id}</dd>
            </div>
          </dl>
          <div className="flow-actions">
            <button type="button" className="btn" onClick={() => setEditingRegistration(true)}>
              Edit registration
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={remove.isPending}
              onClick={() => setDeleteOpen(true)}
            >
              {remove.isPending ? "Deleting…" : "Delete pipeline"}
            </button>
          </div>
          {remove.isError ? <p className="flow-error">{errorText(remove.error)}</p> : null}
          <ConfirmDialog
            open={deleteOpen}
            title="Delete pipeline"
            message={
              record
                ? `Delete “${record.name}”? This removes its registration, stage and guarantee decisions, and agent results.`
                : "Delete this pipeline?"
            }
            confirmLabel="Delete pipeline"
            cancelLabel="Cancel"
            danger
            busy={remove.isPending}
            onCancel={() => {
              if (!remove.isPending) setDeleteOpen(false)
            }}
            onConfirm={() => {
              if (!record) return
              remove.mutate(undefined, {
                onSettled: () => setDeleteOpen(false),
              })
            }}
          />
        </>
      ) : (
        <>
          <label className="flow-label" htmlFor="pipeline-name">
            Display name
            <input
              id="pipeline-name"
              name="pipeline-name"
              className="flow-input"
              value={name}
              onChange={onRegistrationInput}
              required
            />
          </label>
          <fieldset className="flow-fieldset">
            <legend className="flow-label">Code location</legend>
            <div className="flow-choice">
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
            </div>
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
                required
                placeholder="/path/to/pipeline/src"
              />
            </label>
          ) : (
            <div className="flow-grid-2">
              <label className="flow-label flow-span-2" htmlFor="git-url">
                Git URL
                <input
                  id="git-url"
                  name="git-url"
                  className="flow-input"
                  value={gitUrl}
                  onChange={onRegistrationInput}
                  required
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
                />
              </label>
              <label className="flow-label" htmlFor="source-subdir">
                Subfolder
                <input
                  id="source-subdir"
                  name="source-subdir"
                  className="flow-input"
                  value={subdir}
                  onChange={onRegistrationInput}
                  placeholder="src"
                />
              </label>
            </div>
          )}
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
          {register.isError ? <p className="flow-error">{errorText(register.error)}</p> : null}
          <div className="flow-actions">
            <button type="submit" className="btn btn-primary" disabled={register.isPending || name.trim().length === 0}>
              {register.isPending ? "Analyzing…" : locked ? "Re-analyze and save" : "Analyze and register"}
            </button>
            {locked ? (
              <button type="button" className="btn" onClick={() => setEditingRegistration(false)}>
                Cancel
              </button>
            ) : null}
          </div>
        </>
      )}
    </form>
    <section className="card flow-form" id="connector">
      <header className="flow-section-head">
        <div>
          <p className="flow-step">2 · Connector</p>
          <div className="card-title">Where stage output is read</div>
          <p className="card-desc">
            {showConnectorSummary
              ? "Saved on this pipeline. The agent reads stage output from this connection."
              : "Saved on this pipeline. Pick one system, then name the folder or table for each stage."}
          </p>
        </div>
      </header>
      {!locked ? (
        <p className="flow-note">Register the pipeline first. The connector form opens on this pipeline after analysis.</p>
      ) : showConnectorSummary && record?.output_store ? (
        <>
          <ConnectorFacts store={record.output_store} draft={output} />
          <div className="flow-actions">
            <button type="button" className="btn" onClick={() => setEditingConnector(true)}>
              Edit connector
            </button>
          </div>
        </>
      ) : (
        <form className="flow-form" onSubmit={onSaveConnector}>
          <OutputSettings draft={output} stageNames={stageNames} onChange={setOutput} />
          {outputError ? <p className="flow-error">{outputError}</p> : null}
          {saveConnector.isError ? <p className="flow-error">{errorText(saveConnector.error)}</p> : null}
          <div className="flow-actions">
            <button type="submit" className="btn btn-primary" disabled={saveConnector.isPending}>
              {saveConnector.isPending ? "Saving…" : "Save connector"}
            </button>
            {connectorSaved ? (
              <button type="button" className="btn" onClick={() => setEditingConnector(false)}>
                Cancel
              </button>
            ) : null}
          </div>
        </form>
      )}
    </section>
    </div>
  )
}

function ConnectorFacts({
  store,
  draft,
}: {
  store: MinioStore
  draft: OutputDraft
}) {
  const kind = connectorKind(store.type)

  return (
    <dl className="flow-facts">
      <div>
        <dt>System</dt>
        <dd>{kind === "postgres" ? "Postgres" : "MinIO"}</dd>
      </div>
      {kind === "minio" ? (
        <>
          <div>
            <dt>Endpoint</dt>
            <dd className="mono">{store.endpoint || "—"}</dd>
          </div>
          <div>
            <dt>Bucket</dt>
            <dd className="mono">{store.bucket || "—"}</dd>
          </div>
          <div>
            <dt>Folder</dt>
            <dd className="mono">{store.prefix || draft.folder || "—"}</dd>
          </div>
          <div>
            <dt>Layout</dt>
            <dd>{draft.layout === "single" ? "File per stage" : "Subfolder per stage"}</dd>
          </div>
          <div>
            <dt>Access key</dt>
            <dd>{store.access_key || draft.accessKey ? "Set" : "Not set"}</dd>
          </div>
          <div>
            <dt>Secret key</dt>
            <dd>{store.secret_key || draft.secretKey ? "Set" : "Not set"}</dd>
          </div>
        </>
      ) : (
        <>
          <div>
            <dt>Host</dt>
            <dd className="mono">{store.host || "—"}</dd>
          </div>
          <div>
            <dt>Port</dt>
            <dd className="mono">{String(store.port ?? "—")}</dd>
          </div>
          <div>
            <dt>Database</dt>
            <dd className="mono">{store.database || "—"}</dd>
          </div>
          <div>
            <dt>Schema</dt>
            <dd className="mono">{store.db_schema || "—"}</dd>
          </div>
          <div>
            <dt>Username</dt>
            <dd className="mono">{store.username || "—"}</dd>
          </div>
          <div>
            <dt>Password</dt>
            <dd>{store.password || draft.password ? "Set" : "Not set"}</dd>
          </div>
          <div>
            <dt>Layout</dt>
            <dd>{store.db_layout === "shared_table" ? "Shared table" : "One table per stage"}</dd>
          </div>
          {store.db_layout === "shared_table" ? (
            <div>
              <dt>Stage column</dt>
              <dd className="mono">{store.stage_column || "—"}</dd>
            </div>
          ) : null}
        </>
      )}
    </dl>
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
      if (field === "store-kind" && (value === "minio" || value === "postgres")) {
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
      if (field.startsWith("table:")) {
        const stage = field.slice("table:".length)
        onChange({ ...draft, tables: { ...draft.tables, [stage]: value } })
        return
      }
      if (field === "endpoint") onChange({ ...draft, endpoint: value })
      else if (field === "bucket") onChange({ ...draft, bucket: value })
      else if (field === "folder") onChange({ ...draft, folder: value })
      else if (field === "shared-table") onChange({ ...draft, sharedTable: value })
      else if (field === "stage-column") onChange({ ...draft, stageColumn: value })
      else if (field === "host") onChange({ ...draft, host: value })
      else if (field === "port") onChange({ ...draft, port: value })
      else if (field === "database") onChange({ ...draft, database: value })
      else if (field === "username") onChange({ ...draft, username: value })
      else if (field === "password") onChange({ ...draft, password: value })
      else if (field === "db-schema") onChange({ ...draft, dbSchema: value })
      else if (field === "access-key") onChange({ ...draft, accessKey: value })
      else if (field === "secret-key") onChange({ ...draft, secretKey: value })
      else if (field === "http-path") onChange({ ...draft, httpPath: value })
      else if (field === "access-token") onChange({ ...draft, accessToken: value })
      else if (field === "catalog") onChange({ ...draft, catalog: value })
    },
    [draft, onChange],
  )

  return (
    <>
      <fieldset className="connector-kinds">
        <legend className="visually-hidden">Connector type</legend>
        <label className="connector-kind" htmlFor="store-minio">
          <input id="store-minio" className="visually-hidden" type="radio" name="store-kind" value="minio" checked={draft.kind === "minio"} onChange={onInput} />
          <span className="connector-kind-name">MinIO</span>
          <span className="connector-kind-hint">Object storage</span>
        </label>
        <label className="connector-kind" htmlFor="store-postgres">
          <input id="store-postgres" className="visually-hidden" type="radio" name="store-kind" value="postgres" checked={draft.kind === "postgres"} onChange={onInput} />
          <span className="connector-kind-name">Postgres</span>
          <span className="connector-kind-hint">SQL tables</span>
        </label>
      </fieldset>
      <div className="flow-block">
        <h3 className="flow-block-title">Connection</h3>
        {draft.kind === "minio" ? (
          <div className="flow-grid-2">
            <label className="flow-label flow-span-2" htmlFor="minio-endpoint">
              Endpoint
              <input id="minio-endpoint" name="endpoint" className="flow-input" value={draft.endpoint} onChange={onInput} autoComplete="off" />
            </label>
            <label className="flow-label" htmlFor="minio-access-key">
              Access key
              <input id="minio-access-key" name="access-key" className="flow-input" value={draft.accessKey} onChange={onInput} autoComplete="off" />
            </label>
            <label className="flow-label" htmlFor="minio-secret-key">
              Secret key
              <input id="minio-secret-key" name="secret-key" type="password" className="flow-input" value={draft.secretKey} onChange={onInput} autoComplete="new-password" />
            </label>
            <label className="flow-label" htmlFor="minio-bucket">
              Bucket
              <input id="minio-bucket" name="bucket" className="flow-input" value={draft.bucket} onChange={onInput} />
            </label>
          </div>
        ) : null}
        {draft.kind === "postgres" ? (
          <div className="flow-grid-2">
            <label className="flow-label" htmlFor="pg-host">
              Host
              <input id="pg-host" name="host" className="flow-input" value={draft.host} onChange={onInput} autoComplete="off" />
            </label>
            <label className="flow-label" htmlFor="pg-port">
              Port
              <input id="pg-port" name="port" className="flow-input" inputMode="numeric" value={draft.port} onChange={onInput} />
            </label>
            <label className="flow-label" htmlFor="pg-database">
              Database
              <input id="pg-database" name="database" className="flow-input" value={draft.database} onChange={onInput} autoComplete="off" />
            </label>
            <label className="flow-label" htmlFor="pg-schema">
              Schema
              <input id="pg-schema" name="db-schema" className="flow-input" value={draft.dbSchema} onChange={onInput} />
            </label>
            <label className="flow-label" htmlFor="pg-username">
              Username
              <input id="pg-username" name="username" className="flow-input" value={draft.username} onChange={onInput} autoComplete="off" />
            </label>
            <label className="flow-label" htmlFor="pg-password">
              Password
              <input id="pg-password" name="password" type="password" className="flow-input" value={draft.password} onChange={onInput} autoComplete="new-password" />
            </label>
          </div>
        ) : null}
      </div>
      <div className="flow-block">
        <h3 className="flow-block-title">{draft.kind === "minio" ? "Stage folders" : "Stage tables"}</h3>
        {draft.kind === "minio" ? (
          <>
            <label className="flow-label" htmlFor="output-folder">
              Folder
              <input id="output-folder" name="folder" className="flow-input" value={draft.folder} onChange={onInput} />
            </label>
            <fieldset className="flow-fieldset">
              <legend className="flow-label">Layout</legend>
              <div className="flow-choice">
                <label htmlFor="layout-subfolder">
                  <input id="layout-subfolder" type="radio" name="output-layout" value="subfolder" checked={draft.layout === "subfolder"} onChange={onInput} />
                  {" "}One subfolder per stage
                </label>
                <label htmlFor="layout-single">
                  <input id="layout-single" type="radio" name="output-layout" value="single" checked={draft.layout === "single"} onChange={onInput} />
                  {" "}One folder for every stage
                </label>
              </div>
            </fieldset>
          </>
        ) : (
          <>
            <fieldset className="flow-fieldset">
              <legend className="flow-label">How tables are split</legend>
              <div className="flow-choice">
                <label htmlFor="db-per-table">
                  <input id="db-per-table" type="radio" name="db-layout" value="per_table" checked={draft.dbLayout === "per_table"} onChange={onInput} />
                  {" "}One table per stage
                </label>
                <label htmlFor="db-shared-table">
                  <input id="db-shared-table" type="radio" name="db-layout" value="shared_table" checked={draft.dbLayout === "shared_table"} onChange={onInput} />
                  {" "}One table for every stage
                </label>
              </div>
            </fieldset>
            {draft.dbLayout === "shared_table" ? (
              <div className="flow-grid-2">
                <label className="flow-label" htmlFor="shared-table">
                  Table
                  <input id="shared-table" name="shared-table" className="flow-input" value={draft.sharedTable} onChange={onInput} />
                </label>
                <label className="flow-label" htmlFor="stage-column">
                  Stage column
                  <input id="stage-column" name="stage-column" className="flow-input" value={draft.stageColumn} onChange={onInput} />
                </label>
              </div>
            ) : stageNames.length > 0 ? (
              <div className="flow-grid-2">
                {stageNames.map((stage) => (
                  <StageTableField key={stage} stage={stage} value={draft.tables[stage] ?? stage} onInput={onInput} />
                ))}
              </div>
            ) : (
              <p className="flow-note">Stage names become the table names. You can rename them after analysis.</p>
            )}
          </>
        )}
      </div>
    </>
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
        <p className="card-desc">
          Stages listed here are from this registration. Only confirmed stages are watched.
        </p>
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
  const decideOne = useMutation({
    mutationFn: (input: { id: string; status: string }) => {
      if (!detail) throw new Error("No pipeline loaded")
      return api.setOnboardGuarantee(detail.pipeline_id, input.id, input.status)
    },
    onSuccess: () => {
      void onChanged()
    },
  })
  const decideMany = useMutation({
    mutationFn: (decisions: Record<string, string>) => {
      if (!detail) throw new Error("No pipeline loaded")
      return api.setGuaranteeDecisions(detail.pipeline_id, decisions)
    },
    onSuccess: () => {
      void onChanged()
    },
  })
  const busy = decideOne.isPending || decideMany.isPending

  if (loading) return <p className="flow-note">Loading guarantees…</p>
  if (error) return <p className="flow-error">{errorText(error)}</p>
  if (!detail) return null

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <div className="card-title">Confirm guarantees</div>
        <p className="card-desc">
          Guarantees are the findings from this registration&apos;s analysis. Confirmed rules become the checks the agent runs.
        </p>
      </div>
      <div className="flow-row">
        <button
          type="button"
          className="btn"
          disabled={busy || detail.findings.length === 0}
          onClick={() => decideMany.mutate(mapFindings(detail.findings, "confirmed"))}
        >
          Confirm all
        </button>
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
                      <button type="button" className="btn" disabled={busy || status === "confirmed"} onClick={() => decideOne.mutate({ id: finding.id, status: "confirmed" })}>
                        Confirm
                      </button>
                      <button type="button" className="btn" disabled={busy || status === "rejected"} onClick={() => decideOne.mutate({ id: finding.id, status: "rejected" })}>
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

type StoreKind = "minio" | "postgres"
type DbLayout = "per_table" | "shared_table"
type FolderLayout = "subfolder" | "single"

interface OutputDraft {
  kind: StoreKind
  layout: FolderLayout
  folder: string
  endpoint: string
  bucket: string
  secure: boolean
  host: string
  port: string
  database: string
  username: string
  password: string
  dbSchema: string
  accessKey: string
  secretKey: string
  httpPath: string
  accessToken: string
  catalog: string
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
    host: "postgres",
    port: "5432",
    database: "teleguard",
    username: "teleguard",
    password: "",
    dbSchema: "public",
    accessKey: "",
    secretKey: "",
    httpPath: "",
    accessToken: "",
    catalog: "",
    dbLayout: "per_table",
    sharedTable: "",
    stageColumn: "stage",
    tables: {},
  }
}

function connectorKind(savedType: string | undefined): StoreKind {
  if (savedType === "postgres" || savedType === "database") return "postgres"
  return "minio"
}

function outputDraftFromDetail(detail: CodeOnboardDetail): OutputDraft {
  const saved = detail.output_store
  const inferred = inferLayout(saved)
  const names = stageNamesFor(detail)
  const dbLayout = saved?.db_layout === "shared_table" ? "shared_table" : "per_table"
  const blank = emptyOutputDraft()
  return {
    kind: connectorKind(saved?.type),
    layout: inferred.layout,
    folder: inferred.folder,
    endpoint: saved?.endpoint || blank.endpoint,
    bucket: saved?.bucket || blank.bucket,
    secure: saved?.secure ?? false,
    host: saved?.host || blank.host,
    port: String(saved?.port || blank.port),
    database: saved?.database || blank.database,
    username: saved?.username || blank.username,
    password: saved?.password || "",
    dbSchema: saved?.db_schema || blank.dbSchema,
    accessKey: saved?.access_key || "",
    secretKey: saved?.secret_key || "",
    httpPath: saved?.http_path || "",
    accessToken: saved?.access_token || "",
    catalog: saved?.catalog || "",
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
  const port = Number(draft.port)
  return {
    kind: draft.kind,
    endpoint: draft.endpoint.trim(),
    bucket: draft.bucket.trim(),
    prefix: draft.kind === "minio" ? draft.folder.trim().replace(/^\/+|\/+$/g, "") : "",
    secure: draft.secure,
    dsn_env: "STAGE_DATABASE_URL",
    db_layout: draft.kind === "minio" ? "" : draft.dbLayout,
    stage_column: draft.kind !== "minio" && draft.dbLayout === "shared_table" ? draft.stageColumn.trim() : "",
    host: draft.host.trim(),
    port: Number.isInteger(port) ? port : 5432,
    database: draft.database.trim(),
    username: draft.username.trim(),
    password: draft.password,
    db_schema: draft.dbSchema.trim(),
    access_key: draft.accessKey,
    secret_key: draft.secretKey,
    http_path: draft.httpPath.trim(),
    access_token: draft.accessToken,
    catalog: draft.catalog.trim(),
    stages: stages.map((stage) => ({
      stage,
      location: stageLocation(draft.kind, draft.layout, draft.folder, draft.dbLayout, draft.sharedTable, draft.tables, stage),
    })),
  }
}

function validateOutput(draft: OutputDraft, stageNames: string[], editing: boolean): string {
  if (draft.kind === "minio") {
    if (!draft.endpoint.trim()) return "Endpoint is required."
    if (!draft.accessKey.trim()) return "Access key is required."
    if (!draft.secretKey) return "Secret key is required."
    if (!draft.bucket.trim()) return "Bucket is required."
    if (!draft.folder.trim()) return "Folder is required."
    return ""
  }
  if (draft.kind === "postgres") {
    if (!draft.host.trim()) return "Host is required."
    if (!/^\d+$/.test(draft.port.trim()) || Number(draft.port) < 1 || Number(draft.port) > 65535) {
      return "Port must be a number from 1 to 65535."
    }
    if (!draft.database.trim()) return "Database is required."
    if (!draft.username.trim()) return "Username is required."
    if (!draft.password) return "Password is required."
  }
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
  if (store?.type === "database" || store?.type === "postgres") {
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

function locationFor(layout: FolderLayout, folder: string, stage: string): string {
  const base = folder.trim().replace(/^\/+|\/+$/g, "")
  if (!base) return layout === "subfolder" ? `${stage}/` : `${stage}*`
  return layout === "subfolder" ? `${base}/${stage}/` : `${base}/${stage}*`
}

function stageLocation(
  kind: StoreKind,
  layout: FolderLayout,
  folder: string,
  dbLayout: "per_table" | "shared_table",
  sharedTable: string,
  tables: Record<string, string>,
  stage: string,
): string {
  if (kind !== "minio") {
    return dbLayout === "shared_table" ? sharedTable.trim() : (tables[stage] ?? stage).trim()
  }
  return locationFor(layout, folder, stage)
}

function ResultsPanel({
  runs,
  confirmedStages,
  loading,
  error,
}: {
  runs: AgentRun[] | undefined
  confirmedStages: string[]
  loading: boolean
  error: Error | null
}) {
  if (loading) return <p className="flow-note">Loading results…</p>
  if (error) return <p className="flow-error">{errorText(error)}</p>
  const watched = new Set(confirmedStages)
  const rows = [...(runs ?? [])]
    .filter((run) => watched.has(run.stage))
    .reverse()
  if (confirmedStages.length === 0) {
    return (
      <p className="flow-note">
        Confirm at least one stage before monitoring. Results appear only for confirmed stages, and only for files written after that stage was confirmed.
      </p>
    )
  }
  if (rows.length === 0) {
    return (
      <p className="flow-note">
        No files checked yet for the confirmed stages. Changing stage confirm/reject clears prior Results; new files after that show up within a few seconds.
      </p>
    )
  }
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <div className="card-title">Live check results</div>
        <p className="card-desc">
          Newest first for confirmed stages only. Files that existed before a stage was confirmed are not backfilled.
        </p>
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

function mapFindings(
  findings: Array<{ id: string }>,
  status: string,
): Record<string, string> {
  const decisions: Record<string, string> = {}
  for (const finding of findings) decisions[finding.id] = status
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
