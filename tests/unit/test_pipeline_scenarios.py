"""Per-pipeline fault catalogues and payment datagen."""

from __future__ import annotations

from datagen.catalog import generate_for_pipeline
from datagen.generate import GenConfig
from teleguard.inject.scenarios import scenarios_for_pipeline


def test_each_pipeline_has_its_own_scenario_names() -> None:
    web = {s.name for s in scenarios_for_pipeline("web_analytics")}
    user = {s.name for s in scenarios_for_pipeline("user_behavior")}
    pay = {s.name for s in scenarios_for_pipeline("payment_processing")}
    assert "unit_change_android" in web
    assert "text_change_web" in web
    assert "unit_change_android" in user
    assert "action_flood_ios" in user
    assert "text_change_web" not in user
    assert "unit_change_card" in pay
    assert "invalid_status_ach" in pay
    assert "clean" in web & user & pay


def test_payment_generator_shape() -> None:
    batches = generate_for_pipeline("payment_processing")(
        GenConfig(seed=1, n_batches=2, events_per_batch=20)
    )
    assert len(batches) == 2
    event = batches[0][0]
    assert "amount_cents" in event
    assert "payment_method" in event
    assert "payload" not in event


def test_payment_unit_fault_mutates_card_amounts() -> None:
    scenarios = scenarios_for_pipeline("payment_processing", onset_batch=1)
    unit = next(s for s in scenarios if s.name == "unit_change_card")
    batches = generate_for_pipeline("payment_processing")(
        GenConfig(seed=2, n_batches=1, events_per_batch=40)
    )
    before = next(e["amount_cents"] for e in batches[0] if e["payment_method"] == "card")
    mutated, inj = unit.apply(batches)
    after = next(e["amount_cents"] for e in mutated[0] if e["payment_method"] == "card")
    assert after == before / 100.0
    assert inj.field_name == "amount_cents"
