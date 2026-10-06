#!/usr/bin/env python3
"""Claude Code PreToolUse hook: enforces the agent permission boundary.

Blocks (exit code 2, reason on stderr):
- any edit/write under pipelines/*/legacy/    (frozen pipeline, blast-radius control)
- any access to pipelines/*/answer_key/       (sealed ground truth)
- reading .env files                          (secrets stay out of agent context)

Reads the hook payload as JSON on stdin.
"""

from __future__ import annotations

import json
import re
import sys

LEGACY = re.compile(r"(^|/)pipelines/[^/]+/legacy(/|$)")
ANSWER_KEY = re.compile(r"(^|/)pipelines/[^/]+/answer_key(/|$)")
DOTENV = re.compile(r"(^|/)\.env(\.[^/]*)?$")
DOTENV_EXAMPLE = re.compile(r"(^|/)\.env\.example$")

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# Shell writes whose *target* is inside legacy/: a redirect or tee into it, or a mutating
# command naming it. Plain reads (grep, cat) and redirects elsewhere (2>&1) stay allowed.
_LEGACY_PATH = r"['\"]?\S*pipelines/[^/\s]+/legacy"
SHELL_WRITE_INTO_LEGACY = re.compile(
    rf"(>>?\s*{_LEGACY_PATH}"
    rf"|\btee\b(\s+-a)?\s+{_LEGACY_PATH}"
    rf"|\b(sed\s+-i|rm|mv|truncate|chmod|patch)\b[^|;&]*pipelines/[^/\s]+/legacy)"
)


def decide(tool: str, tool_input: dict[str, object]) -> str | None:
    """Return a block reason, or None to allow."""
    keys = ("file_path", "notebook_path", "path")
    path = str(next((tool_input[k] for k in keys if tool_input.get(k)), ""))
    command = str(tool_input.get("command") or "")

    if ANSWER_KEY.search(path) or "answer_key" in command:
        return "Access to the sealed answer key is not allowed (see CLAUDE.md rule 2)."
    if tool in WRITE_TOOLS and LEGACY.search(path):
        return (
            "The legacy pipeline is frozen. Hook lines are added by a human and "
            "listed in HOOKS.md (see CLAUDE.md rule 1)."
        )
    if DOTENV.search(path) and not DOTENV_EXAMPLE.search(path):
        return "Reading or writing .env is not allowed; secrets stay out of agent context."
    if re.search(r"(^|[\s/'\"])\.env(\s|$|['\"])", command):
        return "Commands touching .env are not allowed; secrets stay out of agent context."
    if tool == "Bash" and SHELL_WRITE_INTO_LEGACY.search(command):
        return "Shell writes into the frozen legacy pipeline are not allowed."
    return None


def main() -> int:
    payload = json.load(sys.stdin)
    reason = decide(str(payload.get("tool_name", "")), payload.get("tool_input") or {})
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
