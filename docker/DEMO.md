# Four-container demo

| Container | What it is | Open |
|---|---|---|
| `postgres` | Shipment Ledger stage tables | `localhost:5432`, database `teleguard`, user `teleguard` |
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
   Open **Advanced settings** on that same form before submitting. Match the layout the trigger writes:
   - User Behavior → MinIO, endpoint `http://minio:9000`, bucket `demo`, HTTPS off, layout **Single folder**, folder `demo/user_behavior/outputs` (files `ingest_<run>.csv`, `filter_sessions_<run>.csv`, `aggregate_<run>.csv`)
   - Payment Processing → same endpoint and bucket, layout **Subfolder**, folder `demo/payment_processing/outputs`
   - Web Analytics → same endpoint and bucket, layout **Subfolder**, folder `demo/web_analytics/outputs`
   Shipment Ledger writes Postgres tables `shipment_ledger_landed`, `shipment_ledger_cleaned`, and `shipment_ledger_daily` in database `teleguard`. From the host: `postgresql://teleguard:teleguard@localhost:5432/teleguard` (`STAGE_DATABASE_URL`). Inside Compose the host name is `postgres`.
   A public GitHub or Bitbucket clone URL can be registered with **Remote repository** instead of a local folder. The detection container shallow-clones it, reads the stages, and deletes the checkout. Private repos have no credential field.
2. Sidebar → **Stages**. Confirm the listed stages. Sidebar → **Guarantees**. Confirm the rules to check.
3. Pipeline UI (http://localhost:3000) → choose the **same** pipeline → pick a fault → **Trigger pipeline run**. Status there is whether the job finished. The dropdown also lists the three source shapes: User Behavior (one Python file), Payment Processing (several Python files that share `rules.py`), and Shipment Ledger (SQL `CREATE TABLE` stages, folder `demo/shipment_ledger/outputs`). Web Analytics stays the frozen legacy file.
4. Detection UI sidebar → **Results**. The agent reads `{prefix}/{stage}/` and shows pass/fail. To change the folder later, select the pipeline and open **Source** → **Advanced settings**.

Fault menus are per pipeline. Payment uses amount/status faults. User Behavior uses session-oriented labels; Web Analytics uses page-view / funnel labels (same injectors underneath). Null-user faults finish the job and can fail a null check in detection. Duration-as-text faults fail the job itself.

## Layout

```text
s3://demo/demo/user_behavior/outputs/{stage}_{run_id}.csv
s3://demo/demo/payment_processing/outputs/{stage}/{run_id}.csv
s3://demo/demo/web_analytics/outputs/{stage}/{run_id}.csv
postgres teleguard.shipment_ledger_{stage}   -- localhost:5432, user teleguard
```
