from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.runtime_exec_policy_models import (
    CommandApprovalDecision,
    CommandApprovalDecisionValue,
    ExecApprovalRequirement,
    ExecApprovalRequirementKind,
    Forbidden,
    NeedsApproval,
    Skip,
    parse_exec_approval_requirement_kind,
)


def exec_approval_requirement_for_decision(
    decision: CommandApprovalDecision,
) -> ExecApprovalRequirement:
    if decision.decision is CommandApprovalDecisionValue.ALLOW:
        return Skip()
    if decision.decision is CommandApprovalDecisionValue.PROMPT:
        return NeedsApproval()
    return Forbidden()


def exec_approval_requirement_from_dict(
    payload: Dict[str, Any] | None,
) -> ExecApprovalRequirement:
    data = payload if isinstance(payload, dict) else {}
    requirement = parse_exec_approval_requirement_kind(data.get("requirement"))
    if requirement is ExecApprovalRequirementKind.SKIP:
        return Skip()
    if requirement is ExecApprovalRequirementKind.NEEDS_APPROVAL:
        return NeedsApproval()
    return Forbidden()


def exec_approval_requirement_to_dict(
    requirement: ExecApprovalRequirement,
) -> Dict[str, str]:
    return requirement.to_dict()


def exec_approval_requirement_requires_approval(
    requirement: ExecApprovalRequirement,
) -> bool:
    return isinstance(requirement, NeedsApproval)


def exec_approval_requirement_is_forbidden(
    requirement: ExecApprovalRequirement,
) -> bool:
    return isinstance(requirement, Forbidden)


def exec_approval_requirement_allows_execution(
    requirement: ExecApprovalRequirement,
) -> bool:
    return isinstance(requirement, Skip)


__all__ = [
    "exec_approval_requirement_allows_execution",
    "exec_approval_requirement_for_decision",
    "exec_approval_requirement_from_dict",
    "exec_approval_requirement_is_forbidden",
    "exec_approval_requirement_requires_approval",
    "exec_approval_requirement_to_dict",
]
