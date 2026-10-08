"""Onboard record validation — no real SMTP in unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from teleguard.notify.onboard import OnboardRecord, load_onboard, save_onboard


def test_save_and_load_onboard(tmp_path: Path) -> None:
    path = tmp_path / "onboard.json"
    save_onboard(OnboardRecord("you@example.com", "web_analytics", "git@demo"), path)
    loaded = load_onboard(path)
    assert loaded is not None
    assert loaded.email == "you@example.com"
    assert loaded.pipeline_id == "web_analytics"


def test_rejects_bad_email(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_onboard(OnboardRecord("not-an-email", "web_analytics"), tmp_path / "o.json")
