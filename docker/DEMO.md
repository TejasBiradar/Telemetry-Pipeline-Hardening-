# Three-container demo

| Container | What it is | Open |
|---|---|---|
| `minio` | Where pipeline stage files are stored | http://localhost:9001 (minioadmin / minioadmin) |
| `pipeline` | Pick a reference pipeline, trigger a run, see if the job succeeded | http://localhost:3000 |
| `detection` | Register the pipeline, confirm stages and guarantees, read alerts | http://localhost:8080/source |

## Start

```bash
docker compose up --build
```

## Demo order

1. Detection UI sidebar → **Source**. Register one of:
   - `/app/pipelines/user_behavior/src` (`run.run`)
   - `/app/pipelines/payment_processing/src` (`run.run`)
   - `/app/pipelines/web_analytics/legacy` (`run.run`)
2. Sidebar → **Stages**. Confirm the listed stages. Sidebar → **Guarantees**. Confirm the rules to check.
3. Sidebar → **Outputs**. Choose MinIO, endpoint `http://minio:9000`, bucket `demo`, HTTPS off, layout **Subfolder**. Folder must match the trigger prefix:
   - User Behavior → `demo/user_behavior/outputs`
   - Payment Processing → `demo/payment_processing/outputs`
   - Web Analytics → `demo/web_analytics/outputs`
4. Pipeline UI (http://localhost:3000) → choose the **same** pipeline → pick a fault → **Trigger pipeline run**. Status there is whether the job finished.
5. Detection UI sidebar → **Results**. The agent reads `{prefix}/{stage}/` and shows pass/fail.

Fault menus are per pipeline. Payment uses amount/status faults. User Behavior uses session-oriented labels; Web Analytics uses page-view / funnel labels (same injectors underneath). Null-user faults finish the job and can fail a null check in detection. Duration-as-text faults fail the job itself.

## Layout

```text
s3://demo/demo/user_behavior/outputs/{stage}/{run_id}.csv
s3://demo/demo/payment_processing/outputs/{stage}/{run_id}.csv
s3://demo/demo/web_analytics/outputs/{stage}/{run_id}.csv
```
