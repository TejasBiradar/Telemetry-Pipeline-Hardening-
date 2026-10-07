"""Baseline profiles: what "normal" looks like, per field x segment.

Frozen, not rolling (ADR-8 proposes this as the default: see BUILD_PLAN.md §3.4 "baseline
poisoning" — a rolling baseline would slowly absorb the exact drift we are trying to catch).
Built once from known-clean data, saved to JSON, and reused on every later run until a human
re-approves a new one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

MAX_SAMPLE = 10_000  # PSI/KS/Wasserstein need the real sample, not just mean/std
_TOKEN = re.compile(r"[A-Za-z]+")


@dataclass(frozen=True)
class NumericBaseline:
    sample: tuple[float, ...]  # bounded reference sample, for PSI/KS
    mean: float
    median: float
    std: float
    sample_count: int

    def to_json(self) -> dict[str, Any]:
        return {"sample": list(self.sample), "mean": self.mean, "median": self.median,
                "std": self.std, "sample_count": self.sample_count}

    @staticmethod
    def from_json(d: dict[str, Any]) -> NumericBaseline:
        return NumericBaseline(tuple(d["sample"]), d["mean"], d["median"], d["std"],
                               d["sample_count"])


@dataclass(frozen=True)
class TextBaseline:
    vocabulary: frozenset[str]  # tokens seen in the baseline (for OOV rate)
    template_counts: dict[str, int]  # masked template -> count (for template drift)
    sample_count: int

    def to_json(self) -> dict[str, Any]:
        return {"vocabulary": sorted(self.vocabulary), "template_counts": self.template_counts,
                "sample_count": self.sample_count}

    @staticmethod
    def from_json(d: dict[str, Any]) -> TextBaseline:
        return TextBaseline(frozenset(d["vocabulary"]), dict(d["template_counts"]),
                            d["sample_count"])


@dataclass(frozen=True)
class SegmentVolumeBaseline:
    """Per-batch row counts for one segment, across the baseline-learning batches. Exists
    because an absent segment never appears in a `groupby` — no value-level check (null
    rate, range, drift) can ever see "this client version stopped sending data" on its own,
    which is the brief's own flagship scenario. This is what SegmentVolumeCheck compares
    against."""

    batch_counts: tuple[int, ...]
    median: float

    def to_json(self) -> dict[str, Any]:
        return {"batch_counts": list(self.batch_counts), "median": self.median}

    @staticmethod
    def from_json(d: dict[str, Any]) -> SegmentVolumeBaseline:
        return SegmentVolumeBaseline(tuple(d["batch_counts"]), d["median"])


Key = tuple[str, str, str]  # (checkpoint, field, segment); segment "all" when unsegmented
SegmentKey = tuple[str, str]  # (checkpoint, segment)


@dataclass
class BaselineStore:
    numeric: dict[Key, NumericBaseline] = field(default_factory=dict)
    text: dict[Key, TextBaseline] = field(default_factory=dict)
    segment_volume: dict[SegmentKey, SegmentVolumeBaseline] = field(default_factory=dict)

    def numeric_for(self, checkpoint: str, field_name: str, segment: str | None
                    ) -> NumericBaseline | None:
        return self.numeric.get((checkpoint, field_name, segment or "all"))

    def text_for(self, checkpoint: str, field_name: str, segment: str | None
                ) -> TextBaseline | None:
        return self.text.get((checkpoint, field_name, segment or "all"))

    def set_numeric(self, checkpoint: str, field_name: str, segment: str | None,
                    baseline: NumericBaseline) -> None:
        self.numeric[(checkpoint, field_name, segment or "all")] = baseline

    def set_text(self, checkpoint: str, field_name: str, segment: str | None,
                baseline: TextBaseline) -> None:
        self.text[(checkpoint, field_name, segment or "all")] = baseline

    def segment_volume_for(self, checkpoint: str, segment: str) -> SegmentVolumeBaseline | None:
        return self.segment_volume.get((checkpoint, segment))

    def set_segment_volume(self, checkpoint: str, segment: str,
                           baseline: SegmentVolumeBaseline) -> None:
        self.segment_volume[(checkpoint, segment)] = baseline

    def known_segments(self, checkpoint: str) -> list[str]:
        """Every segment the baseline ever saw at this checkpoint — what "normally present"
        means for SegmentVolumeCheck."""
        return sorted({seg for cp, seg in self.segment_volume if cp == checkpoint})

    def to_json(self) -> dict[str, Any]:
        return {
            "numeric": [{"checkpoint": k[0], "field": k[1], "segment": k[2],
                        **v.to_json()} for k, v in self.numeric.items()],
            "text": [{"checkpoint": k[0], "field": k[1], "segment": k[2],
                      **v.to_json()} for k, v in self.text.items()],
            "segment_volume": [{"checkpoint": k[0], "segment": k[1], **v.to_json()}
                              for k, v in self.segment_volume.items()],
        }

    @staticmethod
    def from_json(d: dict[str, Any]) -> BaselineStore:
        store = BaselineStore()
        for row in d.get("numeric", []):
            store.set_numeric(row["checkpoint"], row["field"], row["segment"],
                              NumericBaseline.from_json(row))
        for row in d.get("text", []):
            store.set_text(row["checkpoint"], row["field"], row["segment"],
                          TextBaseline.from_json(row))
        for row in d.get("segment_volume", []):
            store.set_segment_volume(row["checkpoint"], row["segment"],
                                     SegmentVolumeBaseline.from_json(row))
        return store

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), indent=2, sort_keys=True))

    @staticmethod
    def load(path: Path) -> BaselineStore:
        return BaselineStore.from_json(json.loads(path.read_text()))


def build_numeric_baseline(values: pd.Series) -> NumericBaseline:
    clean = values.dropna().astype(float)
    sample = clean if len(clean) <= MAX_SAMPLE else clean.sample(MAX_SAMPLE, random_state=42)
    return NumericBaseline(
        sample=tuple(sorted(sample.tolist())),
        mean=float(clean.mean()) if len(clean) else 0.0,
        median=float(clean.median()) if len(clean) else 0.0,
        std=float(clean.std()) if len(clean) > 1 else 0.0,
        sample_count=len(clean),
    )


def mask_template(text: str) -> str:
    """Replace digit runs with `<NUM>` so e.g. "retry in 340ms" and "retry in 512ms"
    collapse to one template. A simpler, fully inspectable stand-in for Drain3's tree
    clustering (ADR-7): same goal, no extra dependency, easy to defend under questioning."""
    return re.sub(r"\d+", "<NUM>", text)


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in _TOKEN.finditer(text)]


def build_text_baseline(values: pd.Series) -> TextBaseline:
    clean = values.dropna().astype(str)
    vocabulary = {token for text in clean for token in tokenize(text)}
    templates: dict[str, int] = {}
    for text in clean:
        key = mask_template(text)
        templates[key] = templates.get(key, 0) + 1
    return TextBaseline(vocabulary=frozenset(vocabulary), template_counts=templates,
                        sample_count=len(clean))


def build_segment_volume_baselines(per_batch_dfs: list[pd.DataFrame], segment_column: str,
                                   ) -> dict[str, SegmentVolumeBaseline]:
    """One `SegmentVolumeBaseline` per segment ever seen, built from *separate* per-batch
    frames (never pooled: pooling would lose exactly the per-batch counts this needs)."""
    counts: dict[str, list[int]] = {}
    for df in per_batch_dfs:
        if segment_column not in df.columns:
            continue
        seen_this_batch = set(df[segment_column].dropna().astype(str).unique())
        for segment in seen_this_batch:
            counts.setdefault(segment, []).append(int((df[segment_column] == segment).sum()))
        for segment in set(counts) - seen_this_batch:
            counts[segment].append(0)  # present in an earlier batch, absent in this one
    return {
        segment: SegmentVolumeBaseline(batch_counts=tuple(batch_counts),
                                       median=float(pd.Series(batch_counts).median()))
        for segment, batch_counts in counts.items()
    }
