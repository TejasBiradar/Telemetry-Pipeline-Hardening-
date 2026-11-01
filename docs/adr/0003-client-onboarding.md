# ADR-0003: Client onboarding

- **Status:** Proposed
- **Date:** 2026-10-31
- **Owner:** —
- **Related questions:** first chapter of the production architecture. Runtime collection is out of scope here.

## Context

Onboarding is how a client becomes a pipeline Driftline is allowed to judge. Today `POST /pipelines/code-onboard` takes a display name and exactly one of a local directory or a git URL (`api/schemas.py`, `CodeOnboardIn`). The server assigns the pipeline id. Git is shallow-cloned, analyzed, and the tree is deleted (`teleguard/onboard/code.py`). Stages and guarantees are stored as `pending` until a person confirms them.

That flow has no client account, no record of how results will arrive, and it issues no token. The output-store form asks for a bucket location, which is the lab path, not production onboarding.

## Decision

A pipeline is **inactive** until every gate below has passed. Inactive means the graph is saved and no token has been issued.

### 1. Client

| Case | Result |
|---|---|
| First pipeline for a new customer | Create the client, then the pipeline under it. |
| Another pipeline for a customer who already exists | Attach to that client. New pipeline id. New token later. One token never covers two pipelines. |
| No client name | Reject. A pipeline is not anonymous in production. The lab may keep a single implicit client. |

### 2. Pipeline definition

Exactly one source. Both, or neither, is rejected and nothing is saved. This matches the current function, which raises `provide exactly one of source_path or git_url`.

| Case | Result |
|---|---|
| Git URL, ref, optional subdir | Shallow clone, analyze, delete the tree. Store URL, ref, and subdir. Do not store the source. |
| Local directory | Analyze it. Production stores a content hash of the files read, not a path on a laptop. The lab may still store the path. |
| Path is not a directory, or the URL is not a repo | Reject. Nothing is saved. |
| Folder has no recognizable pipeline | Reject. Stages are not invented. |
| Adapter named `python_pandas` or `sql` | That adapter is used. |
| Adapter omitted, and a Python entry such as `run.run` exists | Python adapter. |
| Adapter omitted, SQL only | SQL adapter. |
| `.env` or another secret file is in the tree | Skip it. Do not copy it into metadata or into an evidence snippet. |

### 3. What the analysis produces

Stages and proposed guarantees, each `pending`. The code graph is stored. Nothing is confirmed by the analysis.

| Case | Result |
|---|---|
| Stage left pending | Not part of the contract. |
| Stage rejected | Stays on the graph so the picture is complete. Not watched. |
| Stage confirmed, and the analysis already has an output location | Stage is eligible. |
| Stage confirmed, and there is no output location | Ask where that stage writes. No answer: the stage returns to pending. |
| Guarantee pending or rejected | Not in the contract. |
| No confirmed stage | Stop. No token. |

### 4. How results will arrive

Record a mode. Do not ask for a bucket password on this screen.

| Case | Mode stored |
|---|---|
| They will add a library call in the task | `library` |
| They will deploy a function on object-created, in their account | `event` |
| The stage is a table in their warehouse | `sql`, plus the table name they type |
| The table is Iceberg or Delta | `manifest` |
| They will not run a collector, and they will grant read | `grant`. The secret is not typed here. |
| They have not chosen | `unset` |
| They refuse every mode | Pipeline stays a saved graph. No token. No monitoring. |

### 5. Token

| Case | Result |
|---|---|
| At least one stage confirmed, and mode is not `unset` | Issue a token. Show it once. Store the hash. |
| Mode `unset`, or no confirmed stage | Do not issue a token. |
| Token lost | Rotate. The previous hash is rejected. |
| Second pipeline | Second token. |

### 6. The definition changes later

| Case | Result |
|---|---|
| They re-analyze the same pipeline | New findings start as `pending`. A stage or guarantee that is still present keeps its previous decision. A stage that disappeared is dropped. |
| They register again as a new pipeline | New id. The old pipeline is left as it was. |

## Consequences

- The lab register screen is a subset: name, path or git, adapter. Client, collector mode, and token are not on that screen yet.
- The output-store form is not part of production onboarding.
- The next chapter is what happens when a run finishes. It is not specified here.
