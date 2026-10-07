from __future__ import annotations

from pathlib import Path

import pandas as pd

from teleguard.checks.gates import NullRateCheck, RangeCheck, VolumeCheck
from teleguard.checks.unit import UnitConsistencyCheck
from teleguard.contracts.factory import build_checks
from teleguard.contracts.model import load_contract
from teleguard.drift.baseline import BaselineStore
from teleguard.drift.numeric import KsCheck, PsiCheck
from teleguard.drift.text import OovRateCheck, TemplateDriftCheck
from teleguard.models import BatchContext

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "pipelines" / "web_analytics" / "contracts.yaml"


def test_load_contract_reads_the_real_web_analytics_draft() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert contract.pipeline == "web_analytics"
    names = [c.checkpoint for c in contract.checkpoints]
    assert names == ["after_ingest", "after_clean", "after_enrich", "after_aggregate"]


def test_for_checkpoint_finds_a_known_checkpoint_and_misses_an_unknown_one() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert contract.for_checkpoint("after_clean") is not None
    assert contract.for_checkpoint("no_such_checkpoint") is None


def test_build_checks_expands_drift_specs_into_two_checks_each() -> None:
    contract = load_contract(CONTRACT_PATH)
    checks = build_checks(contract, "after_clean", BaselineStore())
    kinds = [type(c) for c in checks]
    assert kinds.count(PsiCheck) == 1
    assert kinds.count(KsCheck) == 1
    assert any(isinstance(c, UnitConsistencyCheck) for c in checks)
    assert any(isinstance(c, RangeCheck) for c in checks)
    assert any(isinstance(c, NullRateCheck) for c in checks)


def test_build_checks_expands_text_drift_into_two_checks() -> None:
    contract = load_contract(CONTRACT_PATH)
    checks = build_checks(contract, "after_ingest", BaselineStore())
    kinds = [type(c) for c in checks]
    assert kinds.count(OovRateCheck) == 1
    assert kinds.count(TemplateDriftCheck) == 1


def test_build_checks_includes_a_volume_check_when_the_checkpoint_declares_one() -> None:
    contract = load_contract(CONTRACT_PATH)
    checks = build_checks(contract, "after_ingest", BaselineStore())
    assert any(isinstance(c, VolumeCheck) for c in checks)


def test_build_checks_for_unknown_checkpoint_is_empty() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert build_checks(contract, "no_such_checkpoint", BaselineStore()) == []


def test_built_checks_actually_run_against_a_dataframe() -> None:
    contract = load_contract(CONTRACT_PATH)
    checks = build_checks(contract, "after_enrich", BaselineStore())
    df = pd.DataFrame({"country": ["US", "FR"]})
    ctx = BatchContext(pipeline="web_analytics", batch_id="b1", segment_column="client_version")
    results = [r for c in checks for r in c.run(df, ctx)]
    assert results  # the key-set check ran and produced at least one result
