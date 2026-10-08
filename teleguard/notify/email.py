"""Send alert mail via SMTP. Credentials come from the environment, never from the UI."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    mail_from: str
    # "starttls" (587) or "ssl" (465). Gmail accepts either; WSL often prefers ssl/465.
    security: str = "starttls"


def _load_dotenv_if_present() -> None:
    """Load SMTP_* from repo `.env`. File values win so edits apply after reload."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key.startswith("SMTP_"):
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def smtp_from_env() -> SmtpConfig | None:
    _load_dotenv_if_present()
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    # Gmail app passwords are often pasted with spaces; SMTP wants 16 chars without them.
    password = os.environ.get("SMTP_PASSWORD", "").replace(" ", "").strip()
    mail_from = os.environ.get("SMTP_FROM", user).strip()
    if not host or not user or not password or not mail_from:
        return None
    port = int(os.environ.get("SMTP_PORT", "465"))
    security = os.environ.get("SMTP_SECURITY", "").strip().lower()
    if not security:
        if os.environ.get("SMTP_SSL", "").strip() in ("1", "true", "True"):
            security = "ssl"
        elif os.environ.get("SMTP_TLS", "1") not in ("0", "false", "False"):
            security = "starttls" if port == 587 else "ssl"
        else:
            security = "none"
    if port == 465:
        security = "ssl"
    if port == 587 and security == "ssl":
        security = "starttls"
    return SmtpConfig(host, port, user, password, mail_from, security)


def smtp_configured() -> bool:
    return smtp_from_env() is not None


def send_mail(to: str, subject: str, body: str, config: SmtpConfig | None = None) -> None:
    cfg = config or smtp_from_env()
    if cfg is None:
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD "
            "(and optional SMTP_FROM, SMTP_PORT) in .env"
        )
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.mail_from
    msg["To"] = to
    msg.set_content(body)

    if cfg.security == "ssl":
        with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=45) as smtp:
            smtp.login(cfg.user, cfg.password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(cfg.host, cfg.port, timeout=45) as smtp:
        smtp.ehlo()
        if cfg.security == "starttls":
            smtp.starttls()
            smtp.ehlo()
        smtp.login(cfg.user, cfg.password)
        smtp.send_message(msg)


def alert_email_body(
    *,
    pipeline_id: str,
    scenario: str,
    ui_url: str,
    alerts: list[dict[str, object]],
) -> str:
    lines = [
        f"Driftline alert for pipeline '{pipeline_id}'",
        f"Scenario: {scenario}",
        f"Open: {ui_url}",
        "",
        f"{len(alerts)} alert(s):",
        "",
    ]
    for alert in alerts:
        lines.extend([
            f"- [{alert.get('severity')}] {alert.get('message')}",
            (
                f"  field={alert.get('root_field')} segment={alert.get('segment')} "
                f"first_batch={alert.get('first_batch')}"
            ),
            "",
        ])
    return "\n".join(lines)
