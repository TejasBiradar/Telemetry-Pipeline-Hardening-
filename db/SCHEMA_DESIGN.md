# Database Schema Design: N Pipelines

**Why this design?** Every table has `pipeline_id`, so one database can serve many pipelines. Queries filter by pipeline to keep data isolated.

---

## 1. PIPELINE REGISTRY

```sql
pipelines (id, name, repo_url, commit_sha, froze_at, status)
pipeline_file_checksums (pipeline_id, file_path, sha256)
```

**Purpose:** Register each pipeline and prove it hasn't been tampered with.

**Why:**
- Each pipeline gets a unique `id`
- `repo_url + commit_sha` is the immutable reference (no copying code into our repo)
- `file_checksums` table: one row per file, so CI can verify nothing changed

**Example:**
```sql
INSERT INTO pipelines (name, repo_url, commit_sha) 
VALUES ('web_analytics', 'github.com/foo/analytics', 'abc123...');
-- Returns id = 1

INSERT INTO pipeline_file_checksums (pipeline_id, file_path, sha256)
VALUES (1, 'ingest.py', 'sha256_of_file'), (1, 'clean.py', 'sha256_of_file'), ...;
```

---

## 2. CODE GRAPH

```sql
code_graph_nodes (pipeline_id, node_id, node_type, label, file_path, line_number)
code_graph_edges (pipeline_id, source_node_id, target_node_id, edge_type, evidence_*)
```

**Purpose:** Store the map of the pipeline (functions, fields, data flow) with file:line evidence.

**Why:**
- `node_id` is a unique string like `"field:duration_ms"` or `"fn:clean"`
- Each edge has `evidence_file` and `evidence_line` so you can click through to the code
- `origin` column marks edges as `static` (from code parsing), `runtime` (from execution), or `both`
- Multiple pipelines: each has its own graph (different nodes, different structure)

**Example:**
```sql
INSERT INTO code_graph_nodes (pipeline_id, node_id, node_type, label, file_path, line_number)
VALUES (1, 'field:duration_ms', 'field', 'duration_ms', 'ingest.py', 15);

INSERT INTO code_graph_edges (pipeline_id, source_node_id, target_node_id, edge_type, evidence_file, evidence_line)
VALUES (1, 'field:duration_ms', 'field:duration_s', 'derives', 'clean.py', 24);
```

**Query: what affects this output?**
```sql
WITH RECURSIVE downstream AS (
    SELECT source_node_id, target_node_id 
    FROM code_graph_edges WHERE pipeline_id = 1 AND source_node_id = 'field:duration_ms'
    UNION ALL
    SELECT e.source_node_id, e.target_node_id
    FROM code_graph_edges e
    JOIN downstream d ON e.source_node_id = d.target_node_id
    WHERE e.pipeline_id = 1
)
SELECT DISTINCT target_node_id FROM downstream WHERE target_node_id LIKE 'out:%';
-- Returns: out:avg_load_s, out:p95_load_s
```

---

## 3. GUARANTEES

```sql
pipeline_guarantees (pipeline_id, guarantee_id, kind, field_name, message, file_path, line_number, status, confirmed_by, confirmed_at)
```

**Purpose:** Store confirmed hidden rules, with evidence and confirmation metadata.

**Why:**
- `status` tracks: `pending` (needs review), `confirmed` (verified), `rejected` (false alarm)
- `confirmed_by` and `confirmed_at` track who confirmed it and when
- Each guarantee is `pipeline_id`-specific (web_analytics has different guarantees than payments)
- `kind` column allows filtering: find all "unit_conversion" guarantees across all pipelines

**Example:**
```sql
INSERT INTO pipeline_guarantees 
(pipeline_id, guarantee_id, kind, field_name, message, file_path, line_number, status, confirmed_by, confirmed_at)
VALUES 
(1, 'unit_conversion:duration_ms', 'unit_conversion', 'duration_ms', 
 'assumes duration_ms is in milliseconds',
 'clean.py', 24, 'confirmed', 'smita.p@analytic-edge.com', NOW());
```

**Query: which fields are assumed to be required?**
```sql
SELECT field_name, file_path, line_number 
FROM pipeline_guarantees 
WHERE pipeline_id = 1 AND kind = 'required_field' AND status = 'confirmed';
```

---

## 4. PIPELINE CONFIGS

```sql
pipeline_configs (pipeline_id, hooks_yaml, contracts_yaml, generated_at)
```

**Purpose:** Store the auto-generated configuration for each pipeline.

**Why:**
- `hooks_yaml`: which stages have checkpoints, where checks run
- `contracts_yaml`: what each checkpoint must satisfy (schema, nulls, ranges)
- One row per pipeline, so each pipeline has its own config
- Stored as text so it's easy to read/edit

**Example:**
```yaml
-- Stored in DB as YAML text
pipeline:
  stages:
    - name: clean
      checkpoint: after_clean
      input_rows: 48000
      output_rows: 47900
    - name: enrich
      checkpoint: after_enrich
      output_rows: 47900
```

---

## 5. PIPELINE EXECUTION

```sql
pipeline_runs (pipeline_id, batch_id, input_file, row_count_input, row_count_output, status)
```

**Purpose:** Log each time the pipeline runs.

**Why:**
- `batch_id` is unique per run (e.g., `"2026-10-06_batch_001"`)
- `row_count_input` vs `row_count_output` shows if rows were filtered
- Multiple pipelines: each has its own runs (web_analytics runs independent from payments runs)

**Example:**
```sql
INSERT INTO pipeline_runs (pipeline_id, batch_id, input_file, row_count_input, row_count_output, status)
VALUES (1, '2026-10-06_batch_001', 'data/batch_001.jsonl', 1000, 998, 'success');
```

---

## 6. CHECK RESULTS

```sql
check_results (pipeline_id, run_id, checkpoint, check_name, check_type, status, details)
```

**Purpose:** Store the result of each quality check.

**Why:**
- Each row is one check at one checkpoint on one run
- `status`: pass, warn, fail, error
- `details` is JSON, so it can store anything (expected vs actual, threshold, etc.)
- `checkpoint` column lets you filter "all checks at after_clean" or "all checks at output"

**Example:**
```sql
INSERT INTO check_results (pipeline_id, run_id, checkpoint, check_name, check_type, status, details)
VALUES 
(1, 42, 'after_clean', 'null_rate', 'nulls', 'fail', 
 '{"field": "user_id", "expected_max_null": 0.002, "actual": 0.015}');
```

**Query: what checks failed in the last run?**
```sql
SELECT checkpoint, check_name, status, details
FROM check_results
WHERE pipeline_id = 1 AND run_id = (SELECT MAX(id) FROM pipeline_runs WHERE pipeline_id = 1)
AND status IN ('fail', 'error');
```

---

## 7. ALERTS

```sql
alerts (pipeline_id, run_id, alert_id, severity, field_name, source_segment, message, detection_lag_*)
```

**Purpose:** One alert per problem (deduplicated).

**Why:**
- Deduplication key: `pipeline_id + alert_id`, so the same fault doesn't create 100 alerts
- `source_segment`: "iOS v6.0", "Android v5.1", etc. — identifies which source the problem came from
- `detection_lag_batches` and `detection_lag_seconds`: how quickly was the fault caught?
- Severity is assigned by the alert manager (HIGH = check failed, MEDIUM = drift detected, LOW = warning)

**Example:**
```sql
INSERT INTO alerts (pipeline_id, run_id, alert_id, severity, field_name, source_segment, message, detection_lag_batches)
VALUES 
(1, 42, 'unit_change_duration_iOS_v6_0', 'high', 'duration_ms', 'iOS v6.0',
 'duration_ms mean changed 1000×, likely ms→s conversion',  2);
```

---

## 8. LINEAGE

```sql
lineage_nodes (pipeline_id, node_id, node_type, label)
lineage_edges (pipeline_id, source_node_id, target_node_id, edge_type)
```

**Purpose:** Fast queries for "what does this field affect?"

**Why:**
- Separate from code_graph (which is for all edges: calls, imports, etc.)
- Lineage only follows data links: `field → field → output`
- Lets alerts say "affects error_rate, p95_load_s" (which outputs are impacted)

**Query: if duration_ms breaks, which outputs are affected?**
```sql
WITH RECURSIVE lineage AS (
    SELECT target_node_id FROM lineage_edges 
    WHERE pipeline_id = 1 AND source_node_id = 'field:duration_ms'
    UNION ALL
    SELECT le.target_node_id FROM lineage_edges le
    JOIN lineage l ON le.source_node_id = l.target_node_id
    WHERE le.pipeline_id = 1
)
SELECT label FROM lineage_nodes WHERE pipeline_id = 1 AND node_id IN (SELECT target_node_id FROM lineage)
AND node_type = 'output';
-- Returns: avg_load_s, p95_load_s
```

---

## 9. BASELINE PROFILES

```sql
baseline_profiles (pipeline_id, checkpoint, field_name, segment, p0, p25, p50, p75, p95, p100, mean, stddev, cardinality, null_rate)
```

**Purpose:** Store "normal" for each field, segmented.

**Why:**
- `segment`: "iOS v6.0", "all" if no segmentation
- Drift detection compares current values against baseline
- Multiple segments: "iOS v6.0 baseline differs from Android v5.1 baseline"
- One row per pipeline/checkpoint/field/segment

**Example:**
```sql
INSERT INTO baseline_profiles (pipeline_id, checkpoint, field_name, segment, p50, mean, stddev, null_rate)
VALUES (1, 'after_clean', 'duration_s', 'iOS v6.0', 2.5, 3.1, 1.8, 0.001);
```

---

## 10. DRIFT DETECTIONS

```sql
drift_detections (pipeline_id, run_id, checkpoint, field_name, segment, drift_type, severity, baseline_value, current_value)
```

**Purpose:** Log detected drifts.

**Why:**
- `drift_type`: PSI, KS_test, CUSUM (detected too much change)
- `baseline_value` vs `current_value`: how much changed
- One row per drift detected
- Linked to run and checkpoint, so you know exactly when it happened

**Example:**
```sql
INSERT INTO drift_detections (pipeline_id, run_id, checkpoint, field_name, segment, drift_type, severity, baseline_value, current_value)
VALUES (1, 42, 'after_clean', 'duration_s', 'iOS v6.0', 'psi', 'high', 3.1, 3100.0);
-- mean went from 3.1s to 3100s (1000× change) = high drift
```

---

## 11. EVALUATION

```sql
injections (pipeline_id, injection_id, fault_type, field_affected, details, injected_at)
evaluation_runs (pipeline_id, evaluation_id, baseline_name, status)
evaluation_metrics (pipeline_id, evaluation_run_id, injection_id, check_name, caught, detection_lag_*)
```

**Purpose:** Fault injection + measurement.

**Why:**
- `injections` table: record of intentional faults (ground truth)
- `evaluation_runs`: each evaluation (e.g., "our system vs baseline")
- `evaluation_metrics`: per fault, per check, was it caught? how fast?
- Multiple pipelines: each can be evaluated independently

**Example:**
```sql
-- Record a fault
INSERT INTO injections (pipeline_id, injection_id, fault_type, field_affected, injected_at)
VALUES (1, 'unit_change_001', 'unit_change', 'duration_ms', '2026-10-06 14:00:00');

-- Run evaluation
INSERT INTO evaluation_runs (pipeline_id, evaluation_id, baseline_name, status)
VALUES (1, 'eval_001', 'our_system', 'success');

-- Record results
INSERT INTO evaluation_metrics (pipeline_id, evaluation_run_id, injection_id, check_name, caught, detection_lag_batches)
VALUES (1, 10, 'unit_change_001', 'unit_check', TRUE, 2);
```

---

## 12. SUMMARY

```sql
pipeline_summary (pipeline_id, total_guarantees, confirmed_guarantees, ...)
```

**Purpose:** Aggregate stats per pipeline (for the dashboard scorecard).

**Why:**
- One row per pipeline, keeps query performance fast
- Dashboard shows: "web_analytics: 18/22 guarantees confirmed, 0.95 recall, 85% coverage"
- Updated when guarantees are confirmed, checks run, alerts generated

---

## KEY DESIGN PRINCIPLES

1. **Every table has `pipeline_id`** (except pipelines itself)
   - Queries can filter to one pipeline or aggregate across many
   - Data is naturally isolated by pipeline

2. **Evidence everywhere** (file_path, line_number)
   - Every claim points to where we found it
   - Dashboard can show "click to see the code"

3. **Status and timestamps**
   - Track who confirmed each guarantee and when
   - Track when alerts were generated and how fast they were

4. **Segments**
   - Baseline profiles and drift detection are per-source (iOS, Android, etc.)
   - One fault in one version doesn't get averaged away

5. **Metrics for evaluation**
   - Precision, recall, detection lag, false positives all measurable
   - CI gate can compare baseline vs current

6. **Views for common queries**
   - `v_alerts_with_lineage`: alerts + which outputs are affected
   - `v_evaluation_scorecard`: one-line scorecard per pipeline

---

## Scaling to N pipelines

**Web query:** "Show me all alerts across all pipelines, grouped by field"
```sql
SELECT 
    p.name AS pipeline,
    a.field_name,
    COUNT(*) AS alert_count,
    COUNT(CASE WHEN a.severity = 'high' THEN 1 END) AS high_severity
FROM alerts a
JOIN pipelines p ON a.pipeline_id = p.id
WHERE a.created_at > NOW() - INTERVAL '7 days'
GROUP BY p.name, a.field_name
ORDER BY alert_count DESC;
```

**This just works.** No redesign needed. Queries naturally scale to N pipelines.

---

## Migration strategy

```bash
# 1. Run migration
psql -U postgres teleguard_dev < db/migrations/001_schema_n_pipelines.sql

# 2. Register pipelines
INSERT INTO pipelines (name, repo_url, commit_sha) 
VALUES ('web_analytics', 'github.com/foo/analytics', 'abc123');

# 3. Load code graph, guarantees, results into DB

# 4. Dashboard queries the DB
# 5. CI gate compares metrics from DB
```
