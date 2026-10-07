"""Characterisation test generator: create test cases from confirmed findings.

Each confirmed finding becomes a test case:
- Finding: "unit_conversion in duration_s"
- Test: Inject data with 1000x increase in duration_s, verify it's caught

This replaces the hardcoded 7 cases with dynamic generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from teleguard.findings import Finding, FindingKind


@dataclass
class CharacterisationCase:
    """A single test case to verify the pipeline handles a specific fault."""

    name: str  # e.g., "test_unit_conversion_duration_s"
    finding: Finding
    inject_func: Callable[[pd.DataFrame], pd.DataFrame]  # Injects the fault
    description: str = ""
    expected_result: str = "caught"  # "caught", "missed", "unknown"


class CharacterisationGenerator:
    """Generate test cases from confirmed findings."""

    def __init__(self) -> None:
        self.cases: list[CharacterisationCase] = []

    def generate_from_findings(
        self, findings: list[Finding], confirmed_ids: set[str]
    ) -> list[CharacterisationCase]:
        """Create test cases for all confirmed findings."""
        cases = []

        for finding in findings:
            if finding.finding_id not in confirmed_ids:
                continue

            case = self._case_for_finding(finding)
            if case:
                cases.append(case)

        return cases

    def _case_for_finding(self, finding: Finding) -> CharacterisationCase | None:
        """Map a finding to a test case."""
        field = finding.field or "unknown"

        if finding.kind == FindingKind.UNIT_CONVERSION:
            return CharacterisationCase(
                name=f"test_unit_conversion_{field}",
                finding=finding,
                inject_func=self._inject_unit_conversion(field),
                description=f"Inject 1000x increase in {field}, verify caught",
                expected_result="caught",
            )

        elif finding.kind == FindingKind.REQUIRED_FIELD:
            return CharacterisationCase(
                name=f"test_missing_field_{field}",
                finding=finding,
                inject_func=self._inject_missing_field(field),
                description=f"Remove required field {field}, verify caught",
                expected_result="caught",
            )

        elif finding.kind == FindingKind.ROW_FILTER:
            return CharacterisationCase(
                name="test_row_filter",
                finding=finding,
                inject_func=self._inject_volume_drop(),
                description="Inject significant volume drop, verify caught",
                expected_result="caught",
            )

        elif finding.kind == FindingKind.GROUP_KEY_DROPS_NULLS:
            return CharacterisationCase(
                name=f"test_null_in_key_{field}",
                finding=finding,
                inject_func=self._inject_nulls(field),
                description=f"Add nulls to group key {field}, verify caught",
                expected_result="caught",
            )

        elif finding.kind == FindingKind.DEDUP_KEY:
            return CharacterisationCase(
                name=f"test_duplicate_key_{field}",
                finding=finding,
                inject_func=self._inject_duplicates(field),
                description=f"Introduce duplicates in {field}, verify caught",
                expected_result="caught",
            )

        return None

    @staticmethod
    def _inject_unit_conversion(field: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
        """Inject fault: multiply numeric field by 1000."""

        def inject(df: pd.DataFrame) -> pd.DataFrame:
            if field in df.columns:
                df = df.copy()
                df[field] = df[field] * 1000
            return df

        return inject

    @staticmethod
    def _inject_missing_field(field: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
        """Inject fault: remove a required field."""

        def inject(df: pd.DataFrame) -> pd.DataFrame:
            if field in df.columns:
                df = df.copy()
                df = df.drop(columns=[field])
            return df

        return inject

    @staticmethod
    def _inject_type_change(field: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
        """Inject fault: change column type."""

        def inject(df: pd.DataFrame) -> pd.DataFrame:
            if field in df.columns:
                df = df.copy()
                # Convert to string (common type change)
                df[field] = df[field].astype(str)
            return df

        return inject

    @staticmethod
    def _inject_volume_drop() -> Callable[[pd.DataFrame], pd.DataFrame]:
        """Inject fault: drop 80% of rows."""

        def inject(df: pd.DataFrame) -> pd.DataFrame:
            # Keep only first 20%
            return df.iloc[: max(1, len(df) // 5)].copy()

        return inject

    @staticmethod
    def _inject_nulls(field: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
        """Inject fault: add nulls to a field."""

        def inject(df: pd.DataFrame) -> pd.DataFrame:
            if field in df.columns:
                df = df.copy()
                # Set 50% of values to null
                mask = (pd.Series(range(len(df))) % 2) == 0
                df.loc[mask, field] = None
            return df

        return inject

    @staticmethod
    def _inject_duplicates(field: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
        """Inject fault: create duplicates in a key field."""

        def inject(df: pd.DataFrame) -> pd.DataFrame:
            if field in df.columns:
                df = df.copy()
                # Repeat first row 100 times
                if len(df) > 0:
                    repeat_row = df.iloc[[0]] * 100
                    df = pd.concat([df, repeat_row], ignore_index=True)
            return df

        return inject
