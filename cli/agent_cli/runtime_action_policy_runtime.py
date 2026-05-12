from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from cli.agent_cli import runtime_exec_policy_runtime
from cli.agent_cli import (
    runtime_policy_normalization_helpers_runtime as policy_normalization_service,
)
from cli.agent_cli.runtime_action_policy_models import (
    ActionPolicyDecision,
    ActionPolicyDecisionValue,
    parse_action_policy_decision,
)
from cli.agent_cli.runtime_exec_policy_models import ExecApprovalRequirementKind

if TYPE_CHECKING:
    from cli.agent_cli.gateway_core.browser_actions import BrowserActionClassification


def _decision_for_requirement(requirement: Any) -> ActionPolicyDecisionValue:
    normalized_requirement = str(requirement or "").strip().lower()
    if normalized_requirement == ExecApprovalRequirementKind.NEEDS_APPROVAL.value:
        return ActionPolicyDecisionValue.REQUIRES_APPROVAL
    if normalized_requirement == ExecApprovalRequirementKind.FORBIDDEN.value:
        return ActionPolicyDecisionValue.BLOCKED
    return ActionPolicyDecisionValue.ALLOWED


def _legacy_state_action_policy(
    *,
    action_kind: str,
    state: Dict[str, Any],
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = dict(state.get("payload") or {})
    requirement_payload = dict(state.get("requirement_payload") or {})
    requirement_name = str(requirement_payload.get("requirement") or "").strip().lower()
    policy_decision_name = str(state.get("policy_decision") or "").strip().lower()
    if policy_decision_name in {item.value for item in ActionPolicyDecisionValue}:
        decision = parse_action_policy_decision(policy_decision_name)
    else:
        decision = _decision_for_requirement(requirement_name)
    action_policy = ActionPolicyDecision(
        action_kind=action_kind,
        decision=decision,
        requirement=requirement_name or ExecApprovalRequirementKind.SKIP.value,
        reason_code=str(payload.get("reason_code") or "").strip(),
        reason_text=str(payload.get("reason_text") or "").strip(),
        approval_policy=str(state.get("approval_policy") or "").strip(),
        sandbox_mode=str(state.get("sandbox_mode") or "").strip(),
        matched_rules=payload.get("matched_rules"),
        proposed_rule=payload.get("proposed_rule"),
        normalized_targets=payload.get("normalized_segments"),
        metadata=metadata or {},
    )
    action_policy_payload = action_policy.to_dict()
    payload["action_policy"] = action_policy_payload
    return {
        **dict(state),
        "action_policy": action_policy,
        "action_policy_payload": action_policy_payload,
        "payload": payload,
    }


def evaluate_exec_command_action_policy(
    runtime: Any,
    command: str,
    *,
    workdir: str | None = None,
    sandbox_permissions: str | None = None,
    additional_permissions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = runtime_exec_policy_runtime.evaluate_exec_command_runtime_policy(
        runtime,
        command,
        workdir=workdir,
        sandbox_permissions=sandbox_permissions,
        additional_permissions=additional_permissions,
    )
    metadata: Dict[str, Any] = {}
    normalized_sandbox_permissions = str(sandbox_permissions or "").strip()
    if normalized_sandbox_permissions:
        metadata["requested_sandbox_permissions"] = normalized_sandbox_permissions
    if isinstance(additional_permissions, dict):
        metadata["requested_additional_permissions"] = dict(additional_permissions)
    return _legacy_state_action_policy(
        action_kind="exec_command",
        state=state,
        metadata=metadata or None,
    )


def evaluate_apply_patch_action_policy(
    runtime: Any,
    *,
    patch_text: str,
    workspace_root: Path,
) -> Dict[str, Any]:
    state = runtime_exec_policy_runtime.evaluate_apply_patch_runtime_policy(
        runtime,
        patch_text=patch_text,
        workspace_root=workspace_root,
    )
    return _legacy_state_action_policy(action_kind="apply_patch", state=state)


def _browser_reason(classification: "BrowserActionClassification") -> tuple[str, str]:
    if classification.action_class == "read_only":
        return (
            "browser.read_only.allowed",
            "Browser read-only actions can run without prior approval.",
        )
    if classification.action_class == "external_side_effecting":
        return (
            "browser.external_side_effecting.approval_required",
            "Browser actions with external side effects require approval.",
        )
    return (
        "browser.state_mutating.approval_required",
        "Browser state-mutating actions require approval.",
    )


def _browser_normalized_targets(classification: "BrowserActionClassification") -> tuple[str, ...]:
    items: list[str] = []
    command = str(classification.command or "").strip()
    if command:
        items.append(command)
    action_kind = str(classification.action_kind or "").strip()
    if action_kind and action_kind not in items:
        items.append(action_kind)
    return tuple(items)


def evaluate_browser_action_policy(
    action_type: str,
    *,
    payload: Dict[str, Any] | None = None,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    from cli.agent_cli.gateway_core.browser_actions import classify_browser_action

    classification = classify_browser_action(
        action_type=action_type,
        payload=payload,
        metadata=metadata,
    )
    if classification is None:
        return None
    reason_code, reason_text = _browser_reason(classification)
    requirement = (
        ExecApprovalRequirementKind.SKIP
        if classification.action_class == "read_only"
        else ExecApprovalRequirementKind.NEEDS_APPROVAL
    )
    action_policy = ActionPolicyDecision(
        action_kind="browser",
        decision=_decision_for_requirement(requirement.value),
        requirement=requirement,
        reason_code=reason_code,
        reason_text=reason_text,
        approval_policy=classification.approval_policy,
        matched_rules=(
            {
                "source": "browser_classification",
                "rule_id": f"browser.{classification.action_class}",
                "decision": _decision_for_requirement(requirement.value).value,
                "evidence": {
                    "command": classification.command,
                    "action_kind": classification.action_kind,
                    "action_class": classification.action_class,
                    "audit_stage": classification.audit_stage,
                },
            },
        ),
        normalized_targets=_browser_normalized_targets(classification),
        metadata={
            "action_family": classification.action_family,
            "action_class": classification.action_class,
            "audit_stage": classification.audit_stage,
            "command": classification.command,
            "action_kind": classification.action_kind,
        },
    )
    action_policy_payload = action_policy.to_dict()
    return {
        "classification": classification,
        "approval_required": action_policy.approval_required,
        "action_policy": action_policy,
        "action_policy_payload": action_policy_payload,
        "payload": dict(action_policy_payload),
    }


def evaluate_connector_action_policy(
    *,
    supports_actions: bool,
    approval_policy: str,
) -> Dict[str, Any]:
    normalized_policy = policy_normalization_service.normalize_approval_policy(
        approval_policy,
        default="on-request",
    )
    if not supports_actions:
        requirement = ExecApprovalRequirementKind.SKIP
        reason_code = "connector.no_actions.allowed"
        reason_text = "Connectors without action support do not require approval."
    elif normalized_policy == "never":
        requirement = ExecApprovalRequirementKind.SKIP
        reason_code = "connector.policy_never.allowed"
        reason_text = "Runtime approval policy allows connector actions without prior approval."
    else:
        requirement = ExecApprovalRequirementKind.NEEDS_APPROVAL
        reason_code = "connector.action.approval_required"
        reason_text = "Runtime approval policy requires approval before connector actions."
    action_policy = ActionPolicyDecision(
        action_kind="connector",
        decision=_decision_for_requirement(requirement.value),
        requirement=requirement,
        reason_code=reason_code,
        reason_text=reason_text,
        approval_policy=normalized_policy,
        matched_rules=(
            {
                "source": "connector_contract",
                "rule_id": reason_code,
                "decision": _decision_for_requirement(requirement.value).value,
                "evidence": {
                    "supports_actions": bool(supports_actions),
                    "approval_policy": normalized_policy,
                },
            },
        ),
        normalized_targets=("connector_action",) if supports_actions else ("connector",),
        metadata={
            "supports_actions": bool(supports_actions),
            "resolver": "approvals.resolve",
        },
    )
    action_policy_payload = action_policy.to_dict()
    return {
        "approval_required": action_policy.approval_required,
        "action_policy": action_policy,
        "action_policy_payload": action_policy_payload,
        "payload": {
            "required": action_policy.approval_required,
            "policy": normalized_policy or None,
            "resolver": "approvals.resolve",
            "action_policy": action_policy_payload,
        },
    }


__all__ = [
    "evaluate_apply_patch_action_policy",
    "evaluate_browser_action_policy",
    "evaluate_connector_action_policy",
    "evaluate_exec_command_action_policy",
]
