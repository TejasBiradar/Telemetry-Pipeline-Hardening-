# Three-container demo

| Container | What it is | Open |
|---|---|---|
| `minio` | Where pipeline stage files are stored | http://localhost:9001 (minioadmin / minioadmin) |
| `pipeline` | Trigger a run and see if the job succeeded | http://localhost:3000 |
| `detection` | Register the pipeline, confirm stages and guarantees, read alerts | http://localhost:8080/source |

## Start

```bash
docker compose up --build
```

## Demo order

1. Detection UI sidebar → **Source**. Register `/app/pipelines/user_behavior/src`, entry `run.run`.
2. Sidebar → **Stages**. Confirm `ingest`, `filter_sessions`, `aggregate`. Sidebar → **Guarantees**. Confirm the rules to check.
3. Sidebar → **Outputs**. Choose MinIO, endpoint `http://minio:9000`, bucket `demo`, HTTPS off. For each stage, set a folder such as `demo/user_behavior/outputs/ingest/`, a file, or a pattern. A database table is the other store type.
4. Pipeline UI → pick a fault, then **Trigger pipeline run**. Status there is whether the job finished.
5. Detection UI sidebar → **Results**. The agent reads `{prefix}/{stage}/` and shows pass/fail.

**New nullable (web 1.5.2)** finishes the job and leaves null user ids on the ingest file, so detection can fail the null check. **Type change** fails the job itself.

## Layout

```text
s3://demo/demo/user_behavior/outputs/{stage}/{run_id}.csv
```
