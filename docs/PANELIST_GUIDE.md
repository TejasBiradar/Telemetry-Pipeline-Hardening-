# Panelist Guide: Using Different Pipelines

## Current Setup
The API **discovers every folder under `pipelines/`** that has analyzable source
(`legacy/` by default, or `source_dir` from `pipeline.yaml`). Code graphs are
generated **on the fly** from the adapter — not from hardcoded nodes.

Built-in demos:
- `web_analytics` — frozen under `legacy/` (`default: true`)
- `user_behavior` — agent-maintained under `src/`
- `payment_processing` — agent-maintained under `src/`

## How to Run It With a Different Pipeline

### Option A: Drop a new folder under `pipelines/`
1. Create `pipelines/your_pipeline/` with:
   ```
   pipelines/your_pipeline/
   ├── pipeline.yaml           # name, entry, optional source_dir / default
   ├── legacy/  (or src/)
   │   └── run.py              # The pipeline code to analyze
   ├── HOOKS.md                # Hook instrumentation points
   ├── contracts.yaml          # Data quality checks
   └── review/
       └── decisions.json      # Approval decisions (optional)
   ```
2. Restart the API — it will analyze the new tree automatically.
3. Switch to it in the UI pipeline selector (`GET /pipelines`, `PUT /pipelines/{id}/select`).

### Option B: Switch among the built-in demos
Use the ACTIVE PIPELINE selector in the UI (or `PUT /pipelines/{id}/select`).
Each selection serves that pipeline's on-the-fly graph and findings.

### Option C: What the Panelist Needs to Provide

For **any new pipeline**, they need to provide:

1. **`legacy/run.py`** - The pipeline code to protect
2. **`HOOKS.md`** - List of checkpoints where hooks are inserted
3. **`contracts.yaml`** - Data quality expectations (if they have them)

The system will then **automatically**:
- ✓ Analyze the code graph
- ✓ Reconstruct guarantees (findings.json)
- ✓ Generate the code graph (graph.json)
- ✓ Create checks from contracts.yaml
- ✓ Run evaluation on the pipeline

## How the System Works (for panelists)

### Step 1: Code Graph Generation
```
legacy/run.py → Static Analysis → codegraph/graph.json
```
The system reads the Python code and builds a data-flow graph showing:
- Which functions exist
- How data flows through the pipeline
- Which fields are derived from which

### Step 2: Findings Reconstruction
```
codegraph/graph.json → Pattern Matching → codegraph/findings.json
```
Looks for implicit assumptions in the code:
- "This field is always non-null"
- "This value is always in range 0-100"
- "This text field matches a regex"

### Step 3: Human Approval
```
findings.json → Guarantees Page → decisions.json
```
Panel reviews findings and marks them as:
- ✓ Confirmed (this is a real requirement)
- ✗ Rejected (this is not a requirement)

### Step 4: Check Generation
```
contracts.yaml → Check Factory → Checks at Runtime
```
Creates data quality checks at each pipeline stage:
- Schema validation
- Null rate monitoring
- Range checks
- Drift detection (numeric & text)

### Step 5: Evaluation
```
Pipeline + Checks + Faults → Run Evaluation → Results (86% recall)
```
Injects 8 different faults and measures:
- Precision: Did we only alert on real faults?
- Recall: Did we catch all the faults?
- Lag: How fast did we detect each fault?

## Live Demo Flow

1. **"ACTIVE PIPELINE"** selector at top shows `web_analytics`
2. **"How the System Works"** shows the 5-step flow
3. **"Legacy Pipeline: Before Checks"** shows the problem (corruption silent)
4. **"Live Pipeline Execution"** lets panelist:
   - Select a fault scenario
   - Click "Trigger Data Flow"
   - Watch batches 1-3 pass (green)
   - Watch batches 4-10 fail and get caught (red)
   - See detection summary and alerts

## To Switch Pipelines for the Demo

**Quick way (for demo purposes):**
1. Replace `pipelines/web_analytics/legacy/run.py` with the panelist's pipeline
2. Regenerate: `python -m teleguard.workflow pipelines/your_pipeline`
3. Restart the servers
4. The UI automatically uses the new pipeline

**Note:** The system does NOT yet support hot-swapping pipelines from the UI.  
To do that, we'd need to:
- Add a `/pipeline/switch` endpoint
- Rebuild the AppState when pipeline changes
- Update the Pipeline Selector to call the endpoint

This is a nice-to-have for future work!
