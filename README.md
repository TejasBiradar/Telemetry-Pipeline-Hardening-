# Driftline — Telemetry Pipeline Hardening

C5i capstone brief **#31**. Catch silent damage in telemetry pipelines (unit changes, dropped feeds, nulls, drift) with a code graph, confirmed guarantees, deterministic checks, and alerts — without owning the client’s scheduler or destination.

## What this is

| Layer | Role |
|---|---|
| **Product** | Attach beside a running pipeline (in-process hook or out-of-process tap). Modes: `off` / `observe` / `enforce`. |
| **Lab in this repo** | Reference pipelines under `pipelines/*`, fault injection, evaluation metrics, and a UI to demo the flow. |

Production story: register pipeline source → confirm findings → learn baselines → monitor stage outputs → alert (UI / email / webhook later).  
Demo story: Overview trigger runs a reference pipeline in-process so you can show checks and alerts without a client environment.

See `docs/ARCHITECTURE.md` for design detail.

## Frozen pipelines (`legacy/`)

- **`pipelines/*/legacy/` is frozen.** Do not edit it. It is the pipeline under test.
- Hook lines (if any) are **human-owned** and listed in `pipelines/<name>/HOOKS.md`.
- If a change to `legacy/` seems necessary, stop and explain why — do not patch silently.
- Characterisation tests pin today’s behaviour (including odd crashes). Record oddities in `GUARANTEES.md`; do not “fix” them in characterisation tests.
- Demo pipelines `user_behavior` and `payment_processing` use `source_dir: src` (maintainable). `web_analytics` uses `legacy/`.

Also never commit or read: `pipelines/*/answer_key/`, `.env`, or other secrets.

## Repo layout

| Path | Contents |
|---|---|
| `teleguard/` | Guard, checks, contracts, alerts, adapters, code graph, inject, evaluate, notify |
| `pipelines/` | Reference pipelines + `contracts.yaml`, review decisions, guarantees |
| `api/` | FastAPI service for the UI |
| `ui/` | React dashboard |
| `datagen/` | Seeded synthetic batches |
| `tests/` | Unit, characterisation golden masters, evaluation |
| `docs/` | Architecture, BRD, ADRs, review log, open questions |
| `CLAUDE.md` | Rules for the coding agent |
| `.claudeignore` | Paths agents should not read |

## Quick start

```bash
# Backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt -e .
cp .env.example .env          # add secrets locally; never commit .env
uvicorn api.main:app --reload # http://localhost:8000

# Frontend (separate terminal)
cd ui && npm install && npm run dev   # http://localhost:5173
```

Optional Postgres: `docker compose up -d db` (uses `.env`).

### Checks

```bash
ruff check . && mypy teleguard api && pytest --cov=teleguard
pytest tests/characterisation/ -q   # golden masters for web_analytics
```

### Demo notify (optional)

Set `SMTP_*` in `.env` (see `.env.example`). In the UI, open the person icon next to **API connected** to register an alert email for a pipeline. Welcome mail and scenario alerts use that address when SMTP works.

## Docs worth reading

| Doc | Why |
|---|---|
| `docs/ARCHITECTURE.md` | Attach modes, components |
| `docs/BRD.md` | Problem, acceptance criteria |
| `docs/REQUIREMENTS_AND_OPEN_QUESTIONS.md` | Open panel questions — do not invent answers |
| `docs/REVIEW_LOG.md` | Agent change review record |
| `docs/adr/` | Architecture decisions |
| `TEAM_SPLIT.md` | Team ownership |

## Licence / status

Capstone coursework repo. Not a production SaaS package as-is; the core (`Guard`, checks, contracts) is designed to attach to an external pipeline.
