"""SMTP config parsing — no network."""

from __future__ import annotations

import os

from teleguard.notify import email as email_mod


def test_gmail_465_uses_ssl(monkeypatch: object) -> None:
    monkeypatch.setattr(email_mod, "_load_dotenv_if_present", lambda: None)
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "a@b.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("SMTP_FROM", "a@b.com")
    cfg = email_mod.smtp_from_env()
    assert cfg is not None
    assert cfg.security == "ssl"
    assert cfg.password == "abcdefghijklmnop"


def test_gmail_587_uses_starttls(monkeypatch: object) -> None:
    monkeypatch.setattr(email_mod, "_load_dotenv_if_present", lambda: None)
    for key in list(os.environ):
        if key.startswith("SMTP_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SMTP_USER", "a@b.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcdefghijklmnop")
    monkeypatch.setenv("SMTP_FROM", "a@b.com")
    cfg = email_mod.smtp_from_env()
    assert cfg is not None
    assert cfg.security == "starttls"
