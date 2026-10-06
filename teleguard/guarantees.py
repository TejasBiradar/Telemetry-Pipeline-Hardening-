"""Human review of findings, and the GUARANTEES.md generated from it.

A finding is only a candidate until a person decides on it. Decisions are saved in
`<pipeline>/review/decisions.json`, so review can happen in several sittings, by different
people, and survives re-running the analysis (finding ids are stable).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from teleguard.findings import Finding

Decisions = dict[str, dict[str, Any]]

_TITLES = {
    "unit_conversion": "Unit assumption",
    "required_field": "Required field",
    "row_filter": "Silent row filter",
    "dedup_key": "Duplicate key",
    "default_fill": "Silent default value",
    "unmapped_to_null": "Fixed lookup table",
    "keyword_match": "Keyword matching",
    "string_format": "Text format assumption",
    "timestamp_unit": "Timestamp unit",
    "timezone": "Timezone assumption",
    "group_key_drops_nulls": "Null group keys dropped",
    "runtime_columns": "Columns decided by the data",
    "unused_field": "Unused field",
    "null_lookalike_value": "Value that reads back as missing",
}


def load_decisions(path: Path) -> Decisions:
    decisions: Decisions = json.loads(path.read_text()) if path.exists() else {}
    return decisions


def save_decisions(path: Path, decisions: Decisions) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(decisions, indent=2, sort_keys=True))


def review(findings: list[Finding], decisions: Decisions, reviewer: str, now: str,
           ask: Callable[[str], str] = input) -> Decisions:
    """Ask about every undecided finding. y = confirm, n = reject (asks why), s = skip, q = stop."""
    pending = [f for f in findings if f.finding_id not in decisions]
    for number, finding in enumerate(pending, start=1):
        print(f"\n[{number}/{len(pending)}] {finding.kind.value} on "
              f"'{finding.field or '-'}'")
        print(f"  {finding.evidence.file}:{finding.evidence.line}   {finding.evidence.snippet}")
        print(f"  {finding.message}")
        answer = ask("  Is this a real rule of the pipeline? [y]es / [n]o / [s]kip / [q]uit: ")
        answer = answer.strip().lower()[:1]
        if answer == "q":
            break
        if answer == "y":
            decisions[finding.finding_id] = {"status": "confirmed", "by": reviewer, "at": now}
        elif answer == "n":
            note = ask("  Why not? ").strip()
            decisions[finding.finding_id] = {"status": "rejected", "by": reviewer, "at": now,
                                             "note": note}
    return decisions


def render(pipeline: str, findings: list[Finding], decisions: Decisions,
           observed_behaviour: list[str]) -> str:
    def status(f: Finding) -> str:
        return str(decisions.get(f.finding_id, {}).get("status", "pending"))

    confirmed = [f for f in findings if status(f) == "confirmed"]
    pending = [f for f in findings if status(f) == "pending"]
    rejected = [f for f in findings if status(f) == "rejected"]

    lines = [
        f"# Guarantees: {pipeline}",
        "",
        "> What the pipeline silently assumes. Each rule comes from static analysis of the code,",
        "> and counts as a guarantee only after a person has confirmed it.",
        f"> Status: **{len(confirmed)} confirmed**, {len(pending)} pending review, "
        f"{len(rejected)} rejected.",
        "",
        "## Confirmed",
    ]
    for number, f in enumerate(confirmed, start=1):
        who = decisions[f.finding_id]
        lines += [
            "", f"### G{number}. {_TITLES.get(f.kind.value, f.kind.value)}: {f.field or '-'}",
            f"{f.message}.", "",
            f"- Evidence: `{f.evidence.file}:{f.evidence.line}`  `{f.evidence.snippet}`",
            f"- Confirmed by {who['by']} on {who['at']}",
        ]
    if not confirmed:
        lines += ["", "_None yet._"]

    lines += ["", "## Pending review", "",
              "| Kind | Field | What the code implies | Evidence |", "|---|---|---|---|"]
    lines += [f"| {f.kind.value} | {f.field or '-'} | {f.message} | "
              f"`{f.evidence.file}:{f.evidence.line}` |" for f in pending]
    if not pending:
        lines += ["| _none_ | | | |"]

    lines += ["", "## Rejected", ""]
    lines += [f"- {f.message} (`{f.evidence.file}:{f.evidence.line}`). Reason: "
              f"{decisions[f.finding_id].get('note') or 'none given'}" for f in rejected]
    if not rejected:
        lines += ["_None._"]

    lines += ["", "## Observed behaviour on unusual input",
              "", "> From the characterisation tests. Recorded as-is, not fixed.", ""]
    lines += [f"- {o}" for o in observed_behaviour] or ["_Not run yet._"]
    return "\n".join(lines) + "\n"
