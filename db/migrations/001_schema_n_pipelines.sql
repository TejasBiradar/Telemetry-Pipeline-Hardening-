-- Telemetry Pipeline Hardening: Postgres schema for N pipelines
-- Supports: pipeline registration, code graphs, guarantees, configs, checks, alerts, evaluation
-- Design: every table has pipeline_id, so queries can filter to one or aggregate across many

-- ============================================================================
-- PART 1: PIPELINE REGISTRY
-- ============================================================================

CREATE TABLE pipelines (
    id SERIAL PRIMARY KEY,
    name VARCHAR(256) UNIQUE NOT NULL,              -- e.g., "web_analytics", "payments"
    repo_url VARCHAR(512) NOT NULL,                 -- e.g., "github.com/foo/analytics"
    commit_sha VARCHAR(40) NOT NULL,                -- git commit ID (SHA-1 or SHA-256)
    froze_at TIMESTAMP NOT NULL DEFAULT NOW(),      -- when we locked this version
    language VARCHAR(50),                           -- "python", "sql", "mixed"
    status VARCHAR(50) DEFAULT 'active',            -- active, archived, testing
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_pipelines_name ON pipelines(name);
CREATE INDEX idx_pipelines_status ON pipelines(status);

-- Checksums to detect tampering (one row per file in the frozen pipeline)
CREATE TABLE pipeline_file_checksums (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    file_path VARCHAR(512) NOT NULL,                -- relative path, e.g., "clean.py"
    sha256 VARCHAR(64) NOT NULL,                    -- SHA-256 hash of file content
    recorded_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_checksums_pipeline ON pipeline_file_checksums(pipeline_id);
CREATE UNIQUE INDEX idx_checksums_pipeline_file ON pipeline_file_checksums(pipeline_id, file_path);

-- ============================================================================
-- PART 2: CODE GRAPH (static + runtime analysis)
-- ============================================================================

CREATE TABLE code_graph_nodes (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    node_id VARCHAR(256) NOT NULL,                  -- e.g., "field:duration_ms", "fn:clean", "out:error_rate"
    node_type VARCHAR(50) NOT NULL,                 -- field, function, output, module, stage
    label VARCHAR(256) NOT NULL,                    -- human name, e.g., "duration_ms", "clean", "error_rate"
    file_path VARCHAR(512),                         -- where it's defined
    line_number INTEGER,                            -- line in file
    attrs JSONB,                                    -- extra metadata
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_nodes_pipeline ON code_graph_nodes(pipeline_id);
CREATE INDEX idx_nodes_type ON code_graph_nodes(node_type);
CREATE UNIQUE INDEX idx_nodes_pipeline_id ON code_graph_nodes(pipeline_id, node_id);

CREATE TABLE code_graph_edges (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    source_node_id VARCHAR(256) NOT NULL,           -- from which node
    target_node_id VARCHAR(256) NOT NULL,           -- to which node
    edge_type VARCHAR(50) NOT NULL,                 -- reads, writes, derives, produces, calls, imports, next_stage
    evidence_file VARCHAR(512),                     -- where we found this edge
    evidence_line INTEGER,                          -- line number
    evidence_snippet TEXT,                          -- code snippet
    attrs JSONB,                                    -- formula, role, how, etc.
    origin VARCHAR(50) DEFAULT 'static',            -- static (from code), runtime (from execution), both
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_edges_pipeline ON code_graph_edges(pipeline_id);
CREATE INDEX idx_edges_source ON code_graph_edges(source_node_id);
CREATE INDEX idx_edges_target ON code_graph_edges(target_node_id);
CREATE INDEX idx_edges_type ON code_graph_edges(edge_type);

-- ============================================================================
-- PART 3: GUARANTEES (hidden rules the pipeline assumes)
-- ============================================================================

CREATE TABLE pipeline_guarantees (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    guarantee_id VARCHAR(256) NOT NULL,             -- e.g., "unit_conversion:duration_ms"
    kind VARCHAR(100) NOT NULL,                     -- unit_conversion, required_field, row_filter, etc.
    field_name VARCHAR(256),                        -- which field this is about
    message TEXT NOT NULL,                          -- "duration_ms is in milliseconds"
    file_path VARCHAR(512) NOT NULL,                -- where we found it
    line_number INTEGER NOT NULL,                   -- line in file
    code_snippet TEXT,                              -- the actual code
    impact TEXT,                                    -- "if sent in seconds, metrics 1000× wrong"
    status VARCHAR(50) DEFAULT 'pending',           -- pending, confirmed, rejected
    confirmed_by VARCHAR(256),                      -- email or name who confirmed
    confirmed_at TIMESTAMP,                         -- when confirmed
    rejection_reason TEXT,                          -- if rejected, why
    rejected_by VARCHAR(256),
    rejected_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_guarantees_pipeline ON pipeline_guarantees(pipeline_id);
CREATE INDEX idx_guarantees_status ON pipeline_guarantees(status);
CREATE INDEX idx_guarantees_kind ON pipeline_guarantees(kind);
CREATE INDEX idx_guarantees_field ON pipeline_guarantees(field_name);
CREATE UNIQUE INDEX idx_guarantees_id ON pipeline_guarantees(pipeline_id, guarantee_id);

-- ============================================================================
-- PART 4: PIPELINE CONFIGURATION
-- ============================================================================

CREATE TABLE pipeline_configs (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    hooks_yaml TEXT NOT NULL,                       -- where checks run (stages, checkpoints)
    contracts_yaml TEXT NOT NULL,                   -- what checks enforce (schema, nulls, ranges)
    generated_at TIMESTAMP DEFAULT NOW(),
    generated_from_guarantees_confirmed INTEGER,    -- count of guarantees used
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_configs_pipeline ON pipeline_configs(pipeline_id);

-- ============================================================================
-- PART 5: PIPELINE EXECUTION
-- ============================================================================

CREATE TABLE pipeline_runs (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    batch_id VARCHAR(256) NOT NULL,                 -- unique identifier for this batch
    input_file VARCHAR(512),                        -- path to input data
    row_count_input INTEGER,                        -- rows before pipeline
    row_count_output INTEGER,                       -- rows after pipeline
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(50),                             -- success, failed, blocked
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_runs_pipeline ON pipeline_runs(pipeline_id);
CREATE INDEX idx_runs_status ON pipeline_runs(status);
CREATE INDEX idx_runs_batch_id ON pipeline_runs(batch_id);
CREATE INDEX idx_runs_created ON pipeline_runs(created_at DESC);

-- ============================================================================
-- PART 6: QUALITY CHECKS (gates at each checkpoint)
-- ============================================================================

CREATE TABLE check_results (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    checkpoint VARCHAR(256) NOT NULL,               -- "after_clean", "after_enrich", "output"
    check_name VARCHAR(256) NOT NULL,               -- "schema_check", "null_rate", "drift_numeric"
    check_type VARCHAR(100) NOT NULL,               -- schema, nulls, range, unit, volume, drift
    status VARCHAR(50) NOT NULL,                    -- pass, warn, fail, error
    details JSONB NOT NULL,                         -- {expected: ..., actual: ..., threshold: ...}
    fields_affected VARCHAR[],                      -- array of field names involved
    evaluated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_results_pipeline ON check_results(pipeline_id);
CREATE INDEX idx_results_run ON check_results(run_id);
CREATE INDEX idx_results_checkpoint ON check_results(checkpoint);
CREATE INDEX idx_results_status ON check_results(status);
CREATE INDEX idx_results_type ON check_results(check_type);

-- ============================================================================
-- PART 7: ALERTS (one alert per problem)
-- ============================================================================

CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    alert_id VARCHAR(256) NOT NULL,                 -- unique ID for deduplication
    severity VARCHAR(50) NOT NULL,                  -- high, medium, low
    category VARCHAR(100),                          -- schema_violation, drift, missing_field, unit_change
    field_name VARCHAR(256),                        -- which field triggered it
    source_segment VARCHAR(256),                    -- "iOS v6.0", "Android v5.1", etc.
    message TEXT NOT NULL,                          -- human-readable summary
    detection_lag_batches INTEGER,                  -- how many batches from start to detection
    detection_lag_seconds INTEGER,                  -- seconds to detection
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_alerts_pipeline ON alerts(pipeline_id);
CREATE INDEX idx_alerts_run ON alerts(run_id);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_alerts_field ON alerts(field_name);
CREATE INDEX idx_alerts_created ON alerts(created_at DESC);
CREATE UNIQUE INDEX idx_alerts_id ON alerts(pipeline_id, alert_id);

-- ============================================================================
-- PART 8: LINEAGE (what does each field affect?)
-- ============================================================================

CREATE TABLE lineage_nodes (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    node_id VARCHAR(256) NOT NULL,                  -- from code_graph_nodes
    node_type VARCHAR(50) NOT NULL,                 -- field, output
    label VARCHAR(256) NOT NULL
);

CREATE INDEX idx_lineage_nodes_pipeline ON lineage_nodes(pipeline_id);
CREATE UNIQUE INDEX idx_lineage_nodes_id ON lineage_nodes(pipeline_id, node_id);

CREATE TABLE lineage_edges (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    source_node_id VARCHAR(256) NOT NULL,           -- field or stage
    target_node_id VARCHAR(256) NOT NULL,           -- field or output
    edge_type VARCHAR(50) NOT NULL                  -- derives, produces
);

CREATE INDEX idx_lineage_edges_pipeline ON lineage_edges(pipeline_id);
CREATE INDEX idx_lineage_edges_source ON lineage_edges(source_node_id);
CREATE INDEX idx_lineage_edges_target ON lineage_edges(target_node_id);

-- ============================================================================
-- PART 9: BASELINE PROFILES (for drift detection)
-- ============================================================================

CREATE TABLE baseline_profiles (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    checkpoint VARCHAR(256) NOT NULL,               -- "after_clean", "output"
    field_name VARCHAR(256) NOT NULL,               -- "duration_s", "error_rate"
    segment VARCHAR(256),                           -- "iOS v6.0", "all" if no segment
    -- Numeric fields
    p0 FLOAT,                                       -- min
    p25 FLOAT,
    p50 FLOAT,
    p75 FLOAT,
    p95 FLOAT,
    p100 FLOAT,                                     -- max
    mean FLOAT,
    stddev FLOAT,
    -- Categorical fields
    cardinality INTEGER,
    top_values JSONB,                               -- {value: count, ...}
    null_rate FLOAT,
    -- Metadata
    sample_count INTEGER,                           -- how many rows in baseline
    profile_date TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_profiles_pipeline ON baseline_profiles(pipeline_id);
CREATE INDEX idx_profiles_checkpoint ON baseline_profiles(checkpoint);
CREATE INDEX idx_profiles_field ON baseline_profiles(field_name);
CREATE UNIQUE INDEX idx_profiles_id ON baseline_profiles(pipeline_id, checkpoint, field_name, COALESCE(segment, 'all'));

-- ============================================================================
-- PART 10: DRIFT DETECTION (detected drifts)
-- ============================================================================

CREATE TABLE drift_detections (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    checkpoint VARCHAR(256) NOT NULL,
    field_name VARCHAR(256) NOT NULL,
    segment VARCHAR(256),
    drift_type VARCHAR(50) NOT NULL,                -- psi, ks_test, cusum, template_change, oov
    severity VARCHAR(50) NOT NULL,                  -- high, medium, low
    baseline_value FLOAT,                           -- from baseline_profiles
    current_value FLOAT,                            -- observed in this run
    threshold FLOAT,                                -- what triggered the alert
    message TEXT,
    detected_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_drift_pipeline ON drift_detections(pipeline_id);
CREATE INDEX idx_drift_run ON drift_detections(run_id);
CREATE INDEX idx_drift_field ON drift_detections(field_name);

-- ============================================================================
-- PART 11: EVALUATION (fault injection & results)
-- ============================================================================

CREATE TABLE injections (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    injection_id VARCHAR(256) NOT NULL,             -- e.g., "unit_change_001"
    fault_type VARCHAR(100) NOT NULL,               -- unit_change, missing_field, null_rate_increase, etc.
    field_affected VARCHAR(256),
    severity VARCHAR(50),                           -- high, medium, low
    injected_at TIMESTAMP,                          -- when fault was introduced
    details JSONB,                                  -- {factor: 1000, version: "iOS v6.0", ...}
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_injections_pipeline ON injections(pipeline_id);
CREATE UNIQUE INDEX idx_injections_id ON injections(pipeline_id, injection_id);

CREATE TABLE evaluation_runs (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    evaluation_id VARCHAR(256) NOT NULL,            -- unique ID for this evaluation run
    baseline_name VARCHAR(256),                     -- "no_checks", "schema_only", "our_system"
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(50),                             -- success, failed
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_eval_runs_pipeline ON evaluation_runs(pipeline_id);
CREATE UNIQUE INDEX idx_eval_runs_id ON evaluation_runs(pipeline_id, evaluation_id);

CREATE TABLE evaluation_metrics (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE,
    evaluation_run_id INTEGER REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    injection_id VARCHAR(256),                      -- which fault was this against
    check_name VARCHAR(256),                        -- which check caught it
    caught BOOLEAN,                                 -- did this check catch the fault?
    detection_lag_batches INTEGER,
    detection_lag_seconds INTEGER,
    severity_of_fault VARCHAR(50),
    false_positive_on_clean BOOLEAN,                -- did this check alert on clean data?
    notes TEXT
);

CREATE INDEX idx_metrics_pipeline ON evaluation_metrics(pipeline_id);
CREATE INDEX idx_metrics_eval_run ON evaluation_metrics(evaluation_run_id);
CREATE INDEX idx_metrics_caught ON evaluation_metrics(caught);

-- ============================================================================
-- PART 12: AGGREGATES (summary stats, computed per pipeline)
-- ============================================================================

CREATE TABLE pipeline_summary (
    id SERIAL PRIMARY KEY,
    pipeline_id INTEGER REFERENCES pipelines(id) ON DELETE CASCADE UNIQUE,
    -- Guarantees
    total_guarantees INTEGER DEFAULT 0,
    confirmed_guarantees INTEGER DEFAULT 0,
    rejected_guarantees INTEGER DEFAULT 0,
    pending_guarantees INTEGER DEFAULT 0,
    -- Checks
    total_checks_run INTEGER DEFAULT 0,
    checks_passed INTEGER DEFAULT 0,
    checks_failed INTEGER DEFAULT 0,
    checks_warned INTEGER DEFAULT 0,
    -- Alerts
    total_alerts INTEGER DEFAULT 0,
    high_severity_alerts INTEGER DEFAULT 0,
    -- Evaluation
    detection_precision FLOAT,
    detection_recall FLOAT,
    avg_detection_lag_batches FLOAT,
    false_positive_rate FLOAT,
    equivalence_score FLOAT,                        -- output equivalence %
    coverage_percent FLOAT,                         -- test coverage %
    -- Metadata
    last_run_at TIMESTAMP,
    last_alert_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_summary_pipeline ON pipeline_summary(pipeline_id);

-- ============================================================================
-- VIEWS (for common queries)
-- ============================================================================

-- All alerts for a pipeline, with lineage (which outputs are affected)
CREATE OR REPLACE VIEW v_alerts_with_lineage AS
SELECT
    a.id,
    a.pipeline_id,
    p.name AS pipeline_name,
    a.alert_id,
    a.field_name,
    a.source_segment,
    a.severity,
    a.message,
    -- Find affected outputs via lineage
    STRING_AGG(DISTINCT le2.target_node_id, ', ') AS affected_outputs
FROM alerts a
JOIN pipelines p ON a.pipeline_id = p.id
LEFT JOIN lineage_edges le1 ON a.pipeline_id = le1.pipeline_id
    AND ('field:' || a.field_name) = le1.source_node_id
LEFT JOIN lineage_edges le2 ON a.pipeline_id = le2.pipeline_id
    AND le1.target_node_id = le2.source_node_id
    AND le2.edge_type = 'produces'
GROUP BY a.id, a.pipeline_id, p.name, a.alert_id, a.field_name, a.source_segment, a.severity, a.message;

-- Evaluation scorecard per pipeline
CREATE OR REPLACE VIEW v_evaluation_scorecard AS
SELECT
    p.id,
    p.name,
    ps.confirmed_guarantees,
    ps.total_alerts,
    ps.high_severity_alerts,
    ps.detection_precision,
    ps.detection_recall,
    ps.avg_detection_lag_batches,
    ps.false_positive_rate,
    ps.equivalence_score,
    ps.coverage_percent
FROM pipelines p
LEFT JOIN pipeline_summary ps ON p.id = ps.pipeline_id;

-- ============================================================================
-- GRANTS (for application user)
-- ============================================================================

-- (Run as superuser, then uncomment and adjust user/password)
-- CREATE USER teleguard_app WITH PASSWORD 'secure_password';
-- GRANT USAGE ON SCHEMA public TO teleguard_app;
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO teleguard_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO teleguard_app;
