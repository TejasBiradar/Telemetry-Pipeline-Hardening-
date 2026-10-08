# Hooks: user_behavior

Human-added guard checkpoints (not yet wired into `legacy/run.py`):

| After stage | Suggested call |
|---|---|
| ingest | `df = guard.check("after_ingest", df, ctx)` |
| filter | `df = guard.check("after_filter", df, ctx)` |
| aggregate | `df = guard.check("after_aggregate", df, ctx)` |
