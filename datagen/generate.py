"""Seeded synthetic web-analytics events in the format the web_analytics pipeline ingests.

Same config always gives byte-identical files. Time is injected through `base_ts_ms`.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLATFORMS = ("web", "ios", "android")
VERSIONS = {"web": ("1.4.0", "1.5.2"), "ios": ("6.0.1", "6.1.0"), "android": ("5.1.3", "5.2.0")}
PAGES = ("home", "search", "checkout", "profile")
ACTIONS = ("page_view", "page_view", "page_view", "click", "scroll")
ERRORS = ("timeout while loading", "connection reset", "invalid response")
HOUR_MS = 3_600_000


@dataclass(frozen=True)
class GenConfig:
    seed: int = 42
    n_batches: int = 3
    events_per_batch: int = 300
    base_ts_ms: int = 1_790_000_000_000  # injected clock: no wall-clock reads
    null_user_rate: float = 0.02
    duplicate_rate: float = 0.02
    error_rate: float = 0.05
    slow_rate: float = 0.01  # share of loads that take 300 s or more


def _event(rng: random.Random, cfg: GenConfig, batch: int, index: int) -> dict[str, Any]:
    platform = rng.choices(PLATFORMS, weights=(2, 3, 5))[0]
    slow = rng.random() < cfg.slow_rate
    duration_ms = rng.uniform(300_000, 900_000) if slow else rng.lognormvariate(7.6, 0.6)
    error = rng.choice(ERRORS) if rng.random() < cfg.error_rate else None
    return {
        "event_id": f"b{batch:04d}-e{index:05d}",
        "timestamp": cfg.base_ts_ms + batch * HOUR_MS + rng.randrange(HOUR_MS),
        "user_id": None if rng.random() < cfg.null_user_rate else f"u{rng.randrange(500):04d}",
        "session_id": f"session_{rng.randrange(1, 9):03d}",
        "platform": platform,
        "client_version": rng.choice(VERSIONS[platform]),
        "payload": {
            "page": rng.choice(PAGES),
            "action": rng.choice(ACTIONS),
            "duration_ms": round(duration_ms),
            "error_message": error,
        },
    }


def generate(cfg: GenConfig) -> list[list[dict[str, Any]]]:
    rng = random.Random(cfg.seed)
    batches = []
    for batch in range(1, cfg.n_batches + 1):
        events = [_event(rng, cfg, batch, i) for i in range(cfg.events_per_batch)]
        resent = [e for e in events if rng.random() < cfg.duplicate_rate]
        batches.append(events + resent)
    return batches


def write(cfg: GenConfig, out_dir: Path) -> list[Path]:
    """Write batch_NNNN.jsonl files and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for number, events in enumerate(generate(cfg), start=1):
        path = out_dir / f"batch_{number:04d}.jsonl"
        path.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in events))
        paths.append(path)
    return paths
