# Hooks: payment_processing

Human-added guard checkpoints (not yet wired into `src/run.py`):

| After stage | Suggested call |
|---|---|
| ingest | `df = guard.check("after_ingest", df, ctx)` |
| clean | `df = guard.check("after_clean", df, ctx)` |
| enrich | `df = guard.check("after_enrich", df, ctx)` |
| reconcile | `df = guard.check("after_reconcile", df, ctx)` |
