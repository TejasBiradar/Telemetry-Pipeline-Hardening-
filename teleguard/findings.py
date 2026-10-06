"""Candidate hidden rules found by static analysis. A human must confirm each one."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from teleguard.codegraph.model import Evidence


class FindingKind(str, Enum):
    UNIT_CONVERSION = "unit_conversion"
    ROW_FILTER = "row_filter"
    REQUIRED_FIELD = "required_field"
    DEDUP_KEY = "dedup_key"
    GROUP_KEY_DROPS_NULLS = "group_key_drops_nulls"
    DEFAULT_FILL = "default_fill"
    UNMAPPED_TO_NULL = "unmapped_to_null"
    KEYWORD_MATCH = "keyword_match"
    STRING_FORMAT = "string_format"
    TIMESTAMP_UNIT = "timestamp_unit"
    TIMEZONE = "timezone"
    RUNTIME_COLUMNS = "runtime_columns"
    UNUSED_FIELD = "unused_field"
    NULL_LOOKALIKE_VALUE = "null_lookalike_value"


# Strings that pandas (and most CSV readers) turn into "missing" on read.
NULL_LOOKALIKES = frozenset({"NA", "N/A", "NaN", "nan", "null", "NULL", "None", "none", ""})


@dataclass(frozen=True)
class Finding:
    kind: FindingKind
    field: str | None
    message: str
    evidence: Evidence

    @property
    def finding_id(self) -> str:
        """Stable id used to attach a human decision to this finding."""
        return f"{self.kind.value}:{self.field or '-'}:{self.evidence.file}:{self.evidence.line}"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.finding_id,
            "kind": self.kind.value,
            "field": self.field,
            "message": self.message,
            "evidence": self.evidence.model_dump(),
        }
