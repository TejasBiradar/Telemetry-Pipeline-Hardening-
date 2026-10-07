"""Guard mode and settings from the environment (ARCHITECTURE.md §2: shared, not yet built).

`TELEGUARD_MODE=off` is the instant kill-switch / rollback level 1 (ARCHITECTURE.md §6.3):
it works without redeploying anything, just restarting the process with the env var changed.
"""

from __future__ import annotations

import os

from teleguard.models import GuardMode

_ENV_VAR = "TELEGUARD_MODE"


def guard_mode_from_env(default: GuardMode = GuardMode.OBSERVE) -> GuardMode:
    raw = os.environ.get(_ENV_VAR)
    if raw is None:
        return default
    try:
        return GuardMode(raw.strip().lower())
    except ValueError as exc:
        valid = ", ".join(m.value for m in GuardMode)
        raise ValueError(f"{_ENV_VAR}={raw!r} is not one of: {valid}") from exc
