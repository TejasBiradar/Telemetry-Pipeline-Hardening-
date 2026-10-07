"""End-to-end: generate data, inject every fault, run it through the real web_analytics
pipeline with the guard attached, and check the numbers against both baselines.

Deliberately the slow test in this suite (~100s): realistic batch volume is what makes the
PSI/KS/segment-volume checks statistically meaningful rather than noisy — see
docs/REVIEW_LOG.md entry for the investigation. Everything is seeded, so it is
deterministic, not flaky.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from teleguard.contracts.model import Contract, load_contract
from teleguard.evaluate.baselines import build_baseline_store
from teleguard.evaluate.comparison_systems import b0_no_checks, b1_naive_schema_only, ours
from teleguard.evaluate.engine import evaluate
from teleguard.inject.faults import FaultType
from teleguard.inject.scenarios import FaultScenario, default_scenarios
from teleguard.tracer import load_module

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def legacy() -> ModuleType:
    return load_module(ROOT / "pipelines" / "web_analytics" / "legacy" / "run.py")


@pytest.fixture(scope="module")
def contract() -> Contract:
    return load_contract(ROOT / "pipelines" / "web_analytics" / "contracts.yaml")


@pytest.fixture(scope="module")
def scenarios() -> list[FaultScenario]:
    return default_scenarios(onset_batch=4)


def test_b0_no_checks_catches_nothing_and_crashes_on_type_change(
        legacy: ModuleType, contract: Contract, scenarios: list[FaultScenario]) -> None:
    report = evaluate("B0", legacy, contract, b0_no_checks(), scenarios,
                      n_batches=10, events_per_batch=3000)
    assert report.recall == 0.0
    by_name = {s.scenario_name: s for s in report.scores}
    assert by_name["type_change_android"].crashed_at_batch == 4  # no gate; the pipeline itself breaks


def test_b1_naive_schema_only_catches_only_type_change(
        legacy: ModuleType, contract: Contract, scenarios: list[FaultScenario]) -> None:
    report = evaluate("B1", legacy, contract, b1_naive_schema_only(), scenarios,
                      n_batches=10, events_per_batch=3000)
    by_name = {s.scenario_name: s for s in report.scores}
    assert by_name["type_change_android"].detected
    assert not by_name["unit_change_android"].detected
    assert not by_name["feed_stops_ios"].detected


def test_our_system_substantially_outperforms_both_baselines(
        legacy: ModuleType, contract: Contract, scenarios: list[FaultScenario]) -> None:
    baselines = build_baseline_store(legacy, n_batches=15, events_per_batch=3000)
    report = evaluate("ours", legacy, contract, ours(contract, baselines), scenarios,
                      n_batches=10, events_per_batch=3000)

    assert report.precision == 1.0  # zero false alarms on this seed
    assert report.recall >= 0.75  # 6 of 7 non-clean faults, at minimum
    assert report.mean_lag_batches is not None
    assert report.mean_lag_batches <= 1.0  # caught within the first or second affected batch

    by_name = {s.scenario_name: s for s in report.scores}
    for name in ("unit_change_android", "feed_stops_ios", "new_nullable_web",
                "type_change_android", "volume_drop_android"):
        assert by_name[name].detected, f"{name} should be caught by the real check set"
    assert not by_name["clean"].detected  # the negative control stays quiet


def test_text_change_is_a_known_limitation_not_a_crash(
        legacy: ModuleType, contract: Contract, scenarios: list[FaultScenario]) -> None:
    # error_message is only populated on ~5% of events; for one client_version of one
    # platform that's too few per batch to clear MIN_SAMPLE_SIZE at this volume. Documented
    # honestly rather than hidden (BUILD_PLAN.md guiding principle 7).
    baselines = build_baseline_store(legacy, n_batches=15, events_per_batch=3000)
    report = evaluate("ours", legacy, contract, ours(contract, baselines),
                     [s for s in scenarios if s.name == "text_change_web"],
                     n_batches=10, events_per_batch=3000)
    assert report.scores[0].fault_type is FaultType.TEXT_CHANGE
    assert report.scores[0].crashed_at_batch is None  # it just goes unnoticed, not catastrophic
