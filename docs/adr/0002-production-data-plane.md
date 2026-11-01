# ADR-0002: Production architecture

- **Status:** Proposed
- **Date:** 2026-10-31
- **Owner:** —
- **Related questions:** how Driftline checks client stage output without holding the bucket password, and how that stays small when files are large

## Context

The lab downloads each stage file with a shared MinIO key and loads it with `pd.read_parquet`. That demonstrates register, confirm, and a result. It is not a production system: the password leaves the client, and Driftline's memory grows with the file.

An earlier draft of this ADR put a checker beside the writer and had that checker post pass or fail. That keeps the file in the client zone, and it is still the wrong split for production:

- Driftline cannot re-judge a run when a threshold changes, because the rows and the numbers are gone.
- Numeric drift needs a distribution. A boolean cannot be compared with a baseline later.
- "Install our checker" is only one way to produce those numbers. A warehouse, a bucket event, or a table manifest can produce the same numbers.

The product still does not own the client's scheduler, source, or sink. Pass or fail stays deterministic. Raw events stay in the client boundary. Guard default stays `observe`.

## Options considered

| Option | What moves | Why it loses |
|---|---|---|
| Lab poller with stored bucket keys | The whole file | Password lives in Driftline. One large file can exhaust the API. |
| Checker posts pass or fail | A boolean | Threshold and drift logic are stuck in the client process. A later change of contract cannot be applied to the run that already finished. |
| Driftline always pulls the file | The whole file | Same memory problem, plus a permanent read grant. |
| **Client sends a profile. Driftline decides.** | Kilobytes of counts and histograms | The client can still send false numbers. A check the profile does not contain cannot be answered later. |

## Decision

Driftline stores contracts and decides. The client computes a profile and sends that. The file stays where it was written.

### Control plane (Driftline)

One pipeline token per pipeline, hash at rest, shown once.

| Piece | Role |
|---|---|
| Registry | Code graph, confirmed guarantees, compiled check spec (which columns, which stats) |
| Ingest | Accepts a profile, checks the token, writes one row, returns |
| Queue | Postgres `SKIP LOCKED` between ingest and evaluation. A separate broker is not required at stage-batch volume. |
| Evaluator | Compares the profile with the contract and the frozen baseline. Writes pass, fail, and alerts. No LLM. |
| Store | Profiles, results, alerts, baselines. No stage files. No bucket passwords. |
| UI | Register, confirm, results |

Ingest and evaluation are separate processes so a burst of finished stages does not stall the API.

Worked example, not a measurement: 100 pipelines, 20 stages, 24 runs a day is about 48,000 profiles a day. A profile is on the order of 10 KB (counts plus a fixed histogram per confirmed column). That is under 1 GB a day. Postgres holds it. The API does not grow with file size.

Idempotency key: pipeline id, run id, stage, object etag. A retry does not open a second alert.

### Profile

The only payload that crosses. Versioned.

- From metadata, when the format has it: row count, column names, types. Parquet footer, or Iceberg/Delta manifest.
- Per confirmed column, after a scan only when metadata is not enough: null count, min, max, 32-bucket histogram.
- Per confirmed segment key: top 50 counts plus one "other" bucket. The profile must not grow with a high-cardinality key.
- Text: template-hash counts, capped. A full string scan is not the profile.

Unconfirmed columns are absent from the profile.

### Collectors (client zone)

All four emit the same profile. Driftline does not care which one ran.

1. **Library call in the task.** The worker already holds the table. One call builds the profile from it and posts. No second read. Use this when they will accept a line in the task.
2. **Function on object create.** Their bucket emits "object created." A function in their account, with their bucket role, builds the profile and posts. No change to the DAG, no sidecar on every worker, no URL sent to Driftline. This is the default when they will not touch task code.
3. **SQL, when the stage is already a table.** `count`, null counts, min, max, and histogram buckets run in their warehouse. Their warehouse does the scan. Same profile shape.
4. **Manifest, when the table format already stored stats.** Iceberg or Delta manifests carry row count, null count, min, and max. The collector reads the manifest, not the data files. A histogram is scanned only for a drift check the manifest cannot answer.

Reading raw parquet, when a scan is required: footer first, then confirmed columns, one row group at a time, aggregates kept, row group discarded. Peak memory is one row group of those columns.

### What Driftline does not do

- It does not store a bucket password.
- It does not sit on the write path. `observe` is the default. `enforce` is the collector failing the client task from the same profile, locally.
- A read grant or a one-time URL exists for a client who will not run any collector. A puller, separate from the API, builds the profile and discards the file. Cap of 4 objects in flight per pipeline. This is the exception, not the design.
- No collector and no grant: nothing is checked. A result is not invented.

## Consequences

- The Compose lab stays the prototype: shared MinIO key, full-file load, pass or fail computed in the poller. The presentation names it as a prototype.
- Build order: profile schema and token; ingest plus queue plus evaluator on a profile; one collector (library or object-create function) that posts a profile; manifest and SQL collectors after that; puller last.
- The client can send a profile that does not match the file. Stored numbers can be re-checked against the contract. They cannot prove the file was the source. That is acceptable when the pipeline owner is the customer. It is not an independent audit.
- A guarantee that needs a stat the profile does not hold cannot be evaluated until the collector is updated. The check spec and the profile schema are versioned together.
- Drift and unit checks use the frozen tuning baseline against the histogram. This ADR does not turn those checks on in the lab.
- The code graph is only as true as the adapter input. Python and SQL are the adapters that exist.
