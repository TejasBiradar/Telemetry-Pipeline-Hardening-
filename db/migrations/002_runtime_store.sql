-- Live registration, review, and agent results.
-- Applied by teleguard.pg_store when STAGE_DATABASE_URL or DATABASE_URL is set.
-- Names do not overlap db/migrations/001_schema_n_pipelines.sql.

CREATE TABLE IF NOT EXISTS registered_pipelines (
    pipeline_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    entry TEXT NOT NULL,
    adapter TEXT NOT NULL,
    source_path TEXT NOT NULL DEFAULT '',
    git_url TEXT NOT NULL DEFAULT '',
    git_ref TEXT NOT NULL DEFAULT '',
    source_subdir TEXT NOT NULL DEFAULT '',
    analyzed_at TEXT NOT NULL,
    output_store JSONB,
    graph JSONB NOT NULL,
    document JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS registered_stages (
    pipeline_id TEXT NOT NULL REFERENCES registered_pipelines(pipeline_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    stage_label TEXT NOT NULL,
    stage_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    PRIMARY KEY (pipeline_id, stage_label)
);

CREATE TABLE IF NOT EXISTS registered_guarantees (
    pipeline_id TEXT NOT NULL REFERENCES registered_pipelines(pipeline_id) ON DELETE CASCADE,
    guarantee_id TEXT NOT NULL,
    status TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    field_name TEXT,
    message TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '',
    line_no INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (pipeline_id, guarantee_id)
);

CREATE TABLE IF NOT EXISTS registered_checkpoints (
    pipeline_id TEXT NOT NULL REFERENCES registered_pipelines(pipeline_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    after_stage TEXT NOT NULL,
    attach TEXT NOT NULL,
    location TEXT NOT NULL,
    PRIMARY KEY (pipeline_id, name)
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id BIGSERIAL PRIMARY KEY,
    pipeline_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    checkpoint TEXT NOT NULL,
    object_key TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    failed INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    results JSONB NOT NULL,
    document JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_pipeline ON agent_runs(pipeline_id, id);

CREATE TABLE IF NOT EXISTS check_alerts (
    id BIGSERIAL PRIMARY KEY,
    pipeline_id TEXT NOT NULL,
    run_id BIGINT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    checkpoint TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL,
    field_name TEXT,
    message TEXT NOT NULL DEFAULT '',
    detail JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_check_alerts_pipeline ON check_alerts(pipeline_id, status);

CREATE TABLE IF NOT EXISTS agent_seen_objects (
    pipeline_id TEXT NOT NULL,
    object_key TEXT NOT NULL,
    PRIMARY KEY (pipeline_id, object_key)
);

CREATE TABLE IF NOT EXISTS notify_onboard (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    email TEXT NOT NULL,
    pipeline_id TEXT NOT NULL,
    source_note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS review_decisions (
    pipeline_id TEXT NOT NULL,
    guarantee_id TEXT NOT NULL,
    status TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (pipeline_id, guarantee_id)
);
