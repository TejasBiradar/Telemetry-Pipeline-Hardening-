"""Seeded synthetic payment events for the payment_processing pipeline."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datagen.generate import GenConfig

METHODS = ("card", "ach", "wallet")
STATUSES = ("settled", "settled", "settled", "declined", "pending", "refunded")
MERCHANTS = ("MER_US_01", "MER_US_02", "MER_EU_01", "MER_APAC_01", "MER_OTHER_01")
ERRORS = ("card declined by issuer", "insufficient funds error", None, None, None)
HOUR_MS = 3_600_000


@dataclass(frozen=True)
class PaymentGenConfig:
    seed: int = 42
    n_batches: int = 3
    events_per_batch: int = 300
    base_ts_ms: int = 1_790_000_000_000
    null_user_rate: float = 0.02
    duplicate_rate: float = 0.02


def _event(rng: random.Random, cfg: PaymentGenConfig, batch: int, index: int) -> dict[str, Any]:
    method = rng.choice(METHODS)
    err = rng.choice(ERRORS)
    return {
        "transaction_id": f"txn-b{batch:04d}-{index:05d}",
        "event_ts": cfg.base_ts_ms + batch * HOUR_MS + rng.randrange(HOUR_MS),
        "merchant_id": rng.choice(MERCHANTS),
        "user_id": None if rng.random() < cfg.null_user_rate else f"u{rng.randrange(400):04d}",
        "amount_cents": int(rng.lognormvariate(8.5, 0.7)),
        "currency": "USD",
        "payment_method": method,
        "status": rng.choice(STATUSES),
        "error_message": err,
    }


def generate_payments(cfg: PaymentGenConfig | GenConfig) -> list[list[dict[str, Any]]]:
    """Accept GenConfig or PaymentGenConfig; only shared knobs are used."""
    pcfg = PaymentGenConfig(
        seed=cfg.seed,
        n_batches=cfg.n_batches,
        events_per_batch=cfg.events_per_batch,
        base_ts_ms=getattr(cfg, "base_ts_ms", 1_790_000_000_000),
        null_user_rate=getattr(cfg, "null_user_rate", 0.02),
        duplicate_rate=getattr(cfg, "duplicate_rate", 0.02),
    )
    rng = random.Random(pcfg.seed)
    batches: list[list[dict[str, Any]]] = []
    for batch in range(1, pcfg.n_batches + 1):
        events = [_event(rng, pcfg, batch, i) for i in range(pcfg.events_per_batch)]
        resent = [e for e in events if rng.random() < pcfg.duplicate_rate]
        batches.append(events + resent)
    return batches


def write_payments(cfg: PaymentGenConfig | GenConfig, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for number, events in enumerate(generate_payments(cfg), start=1):
        path = out_dir / f"batch_{number:04d}.jsonl"
        path.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in events))
        paths.append(path)
    return paths
