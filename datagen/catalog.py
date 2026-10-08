"""Pick the right synthetic data generator for a pipeline id."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from datagen.generate import GenConfig, generate
from datagen.payments import generate_payments

Batch = list[dict[str, Any]]
GenerateFn = Callable[[GenConfig], list[Batch]]


def generate_for_pipeline(pipeline_id: str) -> GenerateFn:
    """Return a ``(GenConfig) -> batches`` function for this pipeline's ingest schema."""
    if pipeline_id == "payment_processing":
        return generate_payments
    # web_analytics and user_behavior share the web-analytics JSONL shape
    return generate
