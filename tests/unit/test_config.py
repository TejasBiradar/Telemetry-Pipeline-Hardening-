from __future__ import annotations

import pytest

from teleguard.config import guard_mode_from_env
from teleguard.models import GuardMode


def test_defaults_to_observe_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGUARD_MODE", raising=False)
    assert guard_mode_from_env() == GuardMode.OBSERVE


def test_reads_a_valid_mode_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGUARD_MODE", "off")
    assert guard_mode_from_env() == GuardMode.OFF


def test_is_case_and_whitespace_tolerant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGUARD_MODE", "  ENFORCE  ")
    assert guard_mode_from_env() == GuardMode.ENFORCE


def test_rejects_an_invalid_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGUARD_MODE", "nonsense")
    with pytest.raises(ValueError, match="TELEGUARD_MODE"):
        guard_mode_from_env()
