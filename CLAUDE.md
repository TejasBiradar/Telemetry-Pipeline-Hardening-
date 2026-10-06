# CLAUDE.md: rules for the coding agent on this repo

Project: **Telemetry Pipeline Hardening** (C5i capstone brief #31). Read `docs/ARCHITECTURE.md` before changing structure.

## Hard rules
1. **Never edit `pipelines/*/legacy/`.** That is the pipeline under test and it is frozen. Hook lines are added by a human and listed in `pipelines/<name>/HOOKS.md`. If a change there seems necessary, stop and explain why.
2. **Never read `pipelines/*/answer_key/`, `.env`, or any secret.** The answer key is the sealed ground truth used to score us.
3. **Don't "fix" legacy behaviour.** Characterisation tests pin what the pipeline does *today*, including behaviour that looks wrong. Record oddities in `GUARANTEES.md` instead.
4. **Every claim about the legacy code needs evidence**: file + line. If you can't point to it, say you are unsure.
5. **Checks never modify data and never decide from an LLM.** Pass/fail is deterministic.
6. **Never tune thresholds on the evaluation dataset.** Use the tuning set.
7. **Shared contracts** (`teleguard/models.py`, `db/init/*.sql`, `teleguard/adapters/base.py`, `teleguard/codegraph/model.py`) change only when the user explicitly asks.

## Code standards
- Python ≥ 3.10, type hints everywhere, `mypy --strict` clean, `ruff` clean.
- Every new module has tests in `tests/`. A check is not done until it has a test for: catches its fault, passes on clean data, handles an empty or tiny batch.
- Small functions, clear names, docstrings on public classes and functions only. No commented-out code.
- New dependency → add it to `requirements.txt` with a one-line reason.
- Randomness always takes a seed; time is always injectable in tests.

## Commands
```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt -e .
ruff check . && mypy teleguard && pytest --cov=teleguard
docker compose up -d db        # needs .env (copy .env.example)
```

## Workflow
- Work on a branch; open a pull request; another team member reviews.
- After agent-generated changes, add an entry to `docs/REVIEW_LOG.md`: what was produced, what was changed or rejected, defects caught.
- Record significant decisions as ADRs in `docs/adr/`.
- Open questions for the panel live in `docs/REQUIREMENTS_AND_OPEN_QUESTIONS.md`. Don't assume answers to them.
