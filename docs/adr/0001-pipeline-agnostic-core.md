# ADR-0001: Pipeline-agnostic core with thin adapters

- **Status:** Proposed (team to accept)
- **Date:** 2026-09-28
- **Owner:** Member A
- **Related questions:** Q1, Q2, Q17

## Context
We don't yet know whether a pipeline will be supplied, or in what style (Python, SQL, orchestrated…). We need to start building now without guessing.

## Options considered
| Option | Pros | Cons |
|---|---|---|
| Build for one assumed pipeline | Simplest | Rework if the supplied one differs; nothing reusable |
| **Core on data + common graph format, with per-style adapters** | Start now; works for any pipeline; reusable asset for C5i | A little more interface design up front |
| Fully generic "understands anything" | Sounds impressive | Not achievable honestly; too much scope |

## Decision
- Checks, alerts, lineage, evaluation and UI work on **DataFrames at checkpoints** and a **common code-graph model** (`teleguard/codegraph/model.py`).
- Pipeline-specific code lives only in **adapters** (`teleguard/adapters/base.py`): build the code graph, propose checkpoints.
- Two attach modes: **in-process hook** (one declared line per stage) and **out-of-process tap** (read what a stage wrote; zero code change).
- The first concrete adapter is chosen when we see the pipeline.

## Consequences
- Work on the guard, checks, evaluation, data generator and UI can start before the pipeline exists.
- Every adapter must emit the shared graph format; changes to it need all three members.
- "Works on other pipelines" is claimed only for the adapters we actually build and test.
