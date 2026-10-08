# CLAUDE.md: rules for the coding agent on this repo

Project: **Telemetry Pipeline Hardening** / Driftline (C5i capstone brief #31).

Read `docs/ARCHITECTURE.md` before changing structure. Respect `.claudeignore` (do not read ignored paths). Open questions live in `docs/REQUIREMENTS_AND_OPEN_QUESTIONS.md` — do not invent answers.

## Product shape (do not confuse with the lab)

- The product **attaches beside** a client pipeline (in-process hook or out-of-process tap). It does not own their scheduler, source, or destination.
- `pipelines/*` in this repo are **reference / evaluation** pipelines for demos and metrics. The Overview “Trigger” path runs them in-process for the lab; that is not the production attach story.
- Guard modes: `off` | `observe` | `enforce`. Prefer observe (fail-open) unless the task asks for enforce.

## Hard rules

1. **Never edit `pipelines/*/legacy/`.** 
2. **Never read `pipelines/*/answer_key/`, `.env`, or any secret.** Answer key is sealed scoring ground truth. SMTP and DB credentials stay in `.env` only.
3. **Don't "fix" legacy behaviour.** Characterisation tests pin what the pipeline does *today*, including odd behaviour. Record oddities in `GUARANTEES.md` instead.
4. **Every claim about pipeline source needs evidence:** file + line. If you can't point to it, say you are unsure.
5. **Checks never modify data and never decide from an LLM.** Pass/fail is deterministic.
6. **Never tune thresholds on the evaluation dataset.** Use the tuning set.
7. **Shared contracts** change only when the user explicitly asks:
   - `teleguard/models.py`
   - `teleguard/adapters/base.py`
   - `teleguard/codegraph/model.py`
   - `db/migrations/*.sql` (schema; not `db/init/`)

## Repo map (where to put work)

| Area | Path |
|---|---|
| Guard, checks, contracts, alerts, sinks | `teleguard/` |
| Code graph + adapters | `teleguard/adapters/`, `teleguard/codegraph/`, `teleguard/analyze.py` |
| Faults + evaluation | `teleguard/inject/`, `teleguard/evaluate/`, `datagen/` |
| Pipeline discovery | `teleguard/pipeline_loader.py`, `pipelines/*/pipeline.yaml` |
| Demo notify (email) | `teleguard/notify/` — credentials only via env, never hardcode |
| API / UI | `api/`, `ui/` |
| Docs / ADRs / review log | `docs/` |

Pipelines: `web_analytics` uses `legacy/`; `user_behavior` and `payment_processing` use `source_dir: src` (agents may maintain `src/`, not `legacy/`).

## Code standards

- Python ≥ 3.10, type hints everywhere, `mypy --strict` clean on `teleguard` and `api`, `ruff` clean.
- Every new module has tests in `tests/`. A check is not done until it has tests for: catches its fault, passes on clean data, handles empty or tiny batch.
- Small functions, clear names, docstrings on public classes and functions only. No commented-out code.
- New dependency → add to `requirements.txt` (or `requirements-dev.txt`) with a one-line reason.
- Randomness always takes a seed; time is always injectable in tests.

## Commands

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt -e .
ruff check . && mypy teleguard api && pytest --cov=teleguard
uvicorn api.main:app --reload    # API; baselines built on first need / scenario
cd ui && npm install && npm run dev   # UI at :5173, proxies /api → :8000
```

## Workflow

- Work on a branch; open a pull request; another team member reviews.
- After agent-generated changes, add an entry to `docs/REVIEW_LOG.md`: what was produced, what changed or was rejected, defects caught.
- Record significant decisions as ADRs in `docs/adr/`.
- `.claude/settings.json` + `.claude/hooks/protect_paths.py` enforce protected paths; do not weaken those denies.
