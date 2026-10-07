"""Runs each fault scenario end to end and scores detection against the ground truth.

Matching rule (REQUIREMENTS_AND_OPEN_QUESTIONS.md Q6, our proposed default): an injection
counts as detected if an alert on the same segment is first created within `window` batches
of `onset_batch`. Precision is counted over alerts (every alert that doesn't match some
injection is a false positive); recall is counted over injections (one hit per injection,
no matter how many alerts it produced).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from datagen.generate import GenConfig, generate
from teleguard.alerts.manager import AlertManager
from teleguard.contracts.model import Contract
from teleguard.evaluate.comparison_systems import ChecksFor
from teleguard.evaluate.pipeline_runner import run_batch, write_single_batch
from teleguard.guard import Guard
from teleguard.inject.faults import FaultType, Injection
from teleguard.inject.scenarios import FaultScenario
from teleguard.models import Alert, CheckResult, GuardMode
from teleguard.sinks import MemorySink


@dataclass
class ScenarioRun:
    scenario_name: str
    injection: Injection
    results_by_batch: list[list[CheckResult]]
    alerts: dict[str, Alert]
    alert_first_batch: dict[str, int]
    crashed_at_batch: int | None
    blocked_batches: list[int] = field(default_factory=list)


def run_scenario(legacy: ModuleType, contract: Contract, checks_for: ChecksFor,
                 scenario: FaultScenario, gen_cfg: GenConfig,
                 guard_mode: GuardMode = GuardMode.ENFORCE) -> ScenarioRun:
    base_batches = generate(gen_cfg)
    mutated, injection = scenario.apply(base_batches)

    sink = MemorySink()
    guard = Guard(mode=guard_mode, checks_for=checks_for, sink=sink, alerts=AlertManager())
    results_by_batch: list[list[CheckResult]] = []
    alert_first_batch: dict[str, int] = {}
    crashed_at_batch: int | None = None
    blocked_batches: list[int] = []

    with tempfile.TemporaryDirectory() as tmp:
        for i, events in enumerate(mutated, start=1):
            before = len(sink.results)
            batch_dir = Path(tmp) / f"b{i:04d}"
            write_single_batch(events, batch_dir)
            outcome = run_batch(legacy, batch_dir, contract.pipeline, f"batch_{i:04d}",
                               contract, guard)
            results_by_batch.append(sink.results[before:])
            for alert_id in sink.alerts:
                alert_first_batch.setdefault(alert_id, i)
            if outcome.crashed_at and crashed_at_batch is None:
                crashed_at_batch = i
            if outcome.blocked_at:
                blocked_batches.append(i)

    return ScenarioRun(scenario.name, injection, results_by_batch, dict(sink.alerts),
                       alert_first_batch, crashed_at_batch, blocked_batches)


@dataclass
class ScenarioScore:
    scenario_name: str
    fault_type: FaultType
    detected: bool
    lag_batches: int | None
    matched_alert_id: str | None
    true_positive_alerts: int
    false_positive_alerts: int
    crashed_at_batch: int | None


def score_scenario(run: ScenarioRun, window: int = 5) -> ScenarioScore:
    injection = run.injection
    is_clean = injection.fault_type is FaultType.CLEAN
    window_end = injection.onset_batch + window - 1

    tp = fp = 0
    matched_alert_id: str | None = None
    first_match_batch: int | None = None
    for alert_id, batch in run.alert_first_batch.items():
        alert = run.alerts[alert_id]
        # alert.segment is None for whole-batch checks (schema, whole-batch volume), which
        # can't attribute a fault to one segment but may still have genuinely caught it.
        same_segment = alert.segment is None or alert.segment == injection.segment
        is_match = not is_clean and same_segment and injection.onset_batch <= batch <= window_end
        if is_match:
            tp += 1
            if first_match_batch is None or batch < first_match_batch:
                first_match_batch = batch
                matched_alert_id = alert_id
        else:
            fp += 1

    lag = (first_match_batch - injection.onset_batch) if first_match_batch is not None else None
    return ScenarioScore(run.scenario_name, injection.fault_type, detected=first_match_batch is not None,
                        lag_batches=lag, matched_alert_id=matched_alert_id,
                        true_positive_alerts=tp, false_positive_alerts=fp,
                        crashed_at_batch=run.crashed_at_batch)


@dataclass
class EvaluationReport:
    system_name: str
    scores: list[ScenarioScore]
    precision: float
    recall: float
    mean_lag_batches: float | None

    def detection_matrix(self) -> dict[str, bool]:
        return {s.scenario_name: s.detected for s in self.scores}

    def to_json(self) -> dict[str, object]:
        return {
            "system": self.system_name, "precision": self.precision, "recall": self.recall,
            "mean_lag_batches": self.mean_lag_batches,
            "scenarios": [
                {"scenario": s.scenario_name, "fault_type": s.fault_type.value,
                 "detected": s.detected, "lag_batches": s.lag_batches,
                 "true_positive_alerts": s.true_positive_alerts,
                 "false_positive_alerts": s.false_positive_alerts,
                 "crashed_at_batch": s.crashed_at_batch}
                for s in self.scores
            ],
        }


def evaluate(system_name: str, legacy: ModuleType, contract: Contract, checks_for: ChecksFor,
            scenarios: list[FaultScenario], n_batches: int = 10, events_per_batch: int = 400,
            seed: int = 777, window: int = 5,
            guard_mode: GuardMode = GuardMode.ENFORCE) -> EvaluationReport:
    gen_cfg = GenConfig(seed=seed, n_batches=n_batches, events_per_batch=events_per_batch)
    scores = [score_scenario(run_scenario(legacy, contract, checks_for, s, gen_cfg, guard_mode),
                             window)
             for s in scenarios]

    total_tp = sum(s.true_positive_alerts for s in scores)
    total_fp = sum(s.false_positive_alerts for s in scores)
    non_clean = [s for s in scores if s.fault_type is not FaultType.CLEAN]
    recall = (sum(1 for s in non_clean if s.detected) / len(non_clean)) if non_clean else 0.0
    precision = (total_tp / (total_tp + total_fp)) if (total_tp + total_fp) else 1.0
    lags = [s.lag_batches for s in non_clean if s.lag_batches is not None]
    mean_lag = (sum(lags) / len(lags)) if lags else None

    return EvaluationReport(system_name, scores, precision, recall, mean_lag)
