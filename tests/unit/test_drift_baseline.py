from __future__ import annotations

from pathlib import Path

import pandas as pd

from teleguard.drift.baseline import (
    BaselineStore,
    build_numeric_baseline,
    build_text_baseline,
    mask_template,
    tokenize,
)


def test_build_numeric_baseline_computes_stats() -> None:
    baseline = build_numeric_baseline(pd.Series([1.0, 2.0, 3.0, None]))
    assert baseline.sample_count == 3
    assert baseline.mean == 2.0
    assert baseline.median == 2.0


def test_build_numeric_baseline_caps_sample_size() -> None:
    baseline = build_numeric_baseline(pd.Series(range(20_000)).astype(float))
    assert len(baseline.sample) == 10_000
    assert baseline.sample_count == 20_000


def test_mask_template_collapses_numbers() -> None:
    assert mask_template("retry in 340ms") == mask_template("retry in 512ms")
    assert mask_template("retry in 340ms") == "retry in <NUM>ms"


def test_tokenize_lowercases_words_only() -> None:
    assert tokenize("Timeout 42! connection-reset") == ["timeout", "connection", "reset"]


def test_build_text_baseline_counts_templates_and_vocabulary() -> None:
    baseline = build_text_baseline(pd.Series(["timeout after 10ms", "timeout after 20ms", "ok"]))
    assert baseline.sample_count == 3
    assert "timeout after <NUM>ms" in baseline.template_counts
    assert baseline.template_counts["timeout after <NUM>ms"] == 2
    assert "timeout" in baseline.vocabulary


def test_baseline_store_round_trips_through_json() -> None:
    store = BaselineStore()
    store.set_numeric("cp", "x", "seg", build_numeric_baseline(pd.Series([1.0, 2.0, 3.0])))
    store.set_text("cp", "y", None, build_text_baseline(pd.Series(["hello world"])))

    restored = BaselineStore.from_json(store.to_json())

    assert restored.numeric_for("cp", "x", "seg") == store.numeric_for("cp", "x", "seg")
    assert restored.text_for("cp", "y", None) == store.text_for("cp", "y", None)


def test_baseline_store_saves_and_loads(tmp_path: Path) -> None:
    store = BaselineStore()
    store.set_numeric("cp", "x", None, build_numeric_baseline(pd.Series([1.0, 2.0])))
    path = tmp_path / "baselines.json"

    store.save(path)
    restored = BaselineStore.load(path)

    assert restored.numeric_for("cp", "x", None) == store.numeric_for("cp", "x", None)
