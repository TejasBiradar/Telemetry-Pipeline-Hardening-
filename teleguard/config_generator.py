"""Config generator: create hooks.yaml and contracts.yaml from findings and code graph.

Given:
- Confirmed findings (e.g., "unit_conversion in duration_s")
- Code graph (stages, fields, data flow)
- Baseline profiles (statistics per field)

Generate:
- hooks.yaml: where checks run (checkpoints and check types)
- contracts.yaml: what each checkpoint must satisfy
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from teleguard.codegraph.model import CodeGraph, NodeType
from teleguard.drift.baseline import BaselineStore
from teleguard.findings import Finding, FindingKind
from teleguard.models import CheckType


@dataclass
class HooksConfig:
    """Defines which checks run at each checkpoint."""

    checkpoints: dict[str, list[str]]  # checkpoint → list of check names

    def to_yaml(self) -> str:
        """Serialize to YAML."""
        lines = ["checkpoints:"]
        for cp, checks in sorted(self.checkpoints.items()):
            lines.append(f"  {cp}:")
            for check in checks:
                lines.append(f"    - {check}")
        return "\n".join(lines)


@dataclass
class ContractField:
    """Constraints for a single field at a checkpoint."""

    field_name: str
    field_type: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    max_null_rate: float | None = None  # 0.0 to 1.0
    allowed_values: list[str] | None = None
    constraints: dict[str, str] | None = None  # Free-form additional constraints


@dataclass
class CheckpointContract:
    """Constraints for a checkpoint."""

    checkpoint_name: str
    fields: dict[str, ContractField]  # field_name → constraints

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "checkpoint": self.checkpoint_name,
            "fields": {
                name: {
                    k: v
                    for k, v in {
                        "type": field.field_type,
                        "min": field.min_value,
                        "max": field.max_value,
                        "max_null_rate": field.max_null_rate,
                        "allowed_values": field.allowed_values,
                        **(field.constraints or {}),
                    }.items()
                    if v is not None
                }
                for name, field in self.fields.items()
            },
        }


@dataclass
class ContractsConfig:
    """Defines quality gates per checkpoint."""

    checkpoints: list[CheckpointContract]

    def to_yaml(self) -> str:
        """Serialize to YAML."""
        lines = ["checkpoints:"]
        for cp in self.checkpoints:
            lines.append(f"  - checkpoint: {cp.checkpoint_name}")
            lines.append("    fields:")
            for fname, fconstraints in cp.fields.items():
                lines.append(f"      {fname}:")
                if fconstraints.field_type:
                    lines.append(f"        type: {fconstraints.field_type}")
                if fconstraints.min_value is not None:
                    lines.append(f"        min: {fconstraints.min_value}")
                if fconstraints.max_value is not None:
                    lines.append(f"        max: {fconstraints.max_value}")
                if fconstraints.max_null_rate is not None:
                    lines.append(f"        max_null_rate: {fconstraints.max_null_rate}")
        return "\n".join(lines)


def generate_hooks(
    confirmed_findings: list[Finding], graph: CodeGraph, stages: list[str], confirmed_ids: set[str]
) -> HooksConfig:
    """Generate hooks.yaml from confirmed findings.

    Logic:
    - For each field mentioned in findings, add appropriate checks
    - Route checks to the checkpoint AFTER the field is created/processed
    """
    hooks: dict[str, list[str]] = {}

    # Initialize checkpoints
    for stage in stages:
        checkpoint = f"after_{stage}"
        hooks[checkpoint] = []

    hooks["output"] = []

    # Map findings to checks
    for finding in confirmed_findings:
        if finding.finding_id not in confirmed_ids:
            continue

        if finding.field is None:
            continue

        field_node_id = f"field:{finding.field}"
        if not graph.has_node(field_node_id):
            continue

        # Determine which checkpoint this field belongs to
        checkpoint = _find_checkpoint_for_field(field_node_id, graph, stages)
        if checkpoint and checkpoint in hooks:
            # Add appropriate check based on finding type
            check_name = _check_for_finding(finding)
            if check_name and check_name not in hooks[checkpoint]:
                hooks[checkpoint].append(check_name)

    return HooksConfig(checkpoints=hooks)


def generate_contracts(
    confirmed_findings: list[Finding],
    graph: CodeGraph,
    baselines: BaselineStore,
    stages: list[str],
    confirmed_ids: set[str],
) -> ContractsConfig:
    """Generate contracts.yaml from findings and baselines.

    Logic:
    - Extract field constraints from findings
    - Use baseline statistics to infer ranges
    - Create CheckpointContract for each stage
    """
    checkpoints: list[CheckpointContract] = []

    for stage in stages:
        checkpoint_name = f"after_{stage}"
        fields: dict[str, ContractField] = {}

        # Add constraints for fields mentioned in confirmed findings
        for finding in confirmed_findings:
            if finding.finding_id not in confirmed_ids:
                continue

            if finding.field is None:
                continue

            # Check if this field is created/modified by this stage
            # (simplified: just add to first matching checkpoint)
            field = finding.field

            if field not in fields:
                # Infer constraints from baseline and finding
                field_constraints = ContractField(field_name=field)

                # Try to get baseline profile (simplified for now)
                # In practice, you'd query baselines.get(field, segment) per the BaselineStore API
                fields[field] = field_constraints

        if fields:
            checkpoints.append(CheckpointContract(checkpoint_name=checkpoint_name, fields=fields))

    return ContractsConfig(checkpoints=checkpoints)


def _find_checkpoint_for_field(field_node_id: str, graph: CodeGraph, stages: list[str]) -> str | None:
    """Determine which checkpoint a field belongs to (where it's created/modified).

    Simplified: return the last stage (assuming field is computed/available by end).
    Better: trace stage boundaries in the code graph.
    """
    if stages:
        return f"after_{stages[-1]}"
    return None


def _check_for_finding(finding: Finding) -> str | None:
    """Map a finding type to a check name.

    Example:
    - FindingKind.UNIT_CONVERSION → "unit:field_name"
    - FindingKind.REQUIRED_FIELD → "schema"
    """
    field = finding.field or "unknown"
    mapping: dict[FindingKind, str] = {
        FindingKind.UNIT_CONVERSION: f"unit:{field}",
        FindingKind.REQUIRED_FIELD: "schema",
        FindingKind.ROW_FILTER: "volume",
        FindingKind.DEDUP_KEY: f"dup:{field}",
        FindingKind.GROUP_KEY_DROPS_NULLS: f"null_group:{field}",
    }
    return mapping.get(finding.kind)
