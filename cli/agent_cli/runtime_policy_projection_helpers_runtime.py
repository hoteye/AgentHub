from __future__ import annotations

from typing import Any

from cli.agent_cli import (
    runtime_policy_normalization_helpers_runtime as normalization_service,
)


SHELL_POLICY_DECISIONS = ("allowed", "blocked", "requires_approval")


def shell_policy_decision_contract(
    *,
    approval_policy: str | None,
    sandbox_mode: str | None,
    network_access_enabled: bool | None,
    request_permission_enabled: bool | None,
    requires_approval: bool,
    blocked: bool,
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    if blocked:
        decision = "blocked"
        reason = str(blocked_reason or "policy_denied").strip() or "policy_denied"
    elif requires_approval:
        decision = "requires_approval"
        reason = "approval_required"
    else:
        decision = "allowed"
        reason = "policy_allowed"
    if decision not in SHELL_POLICY_DECISIONS:
        decision = "blocked"
        reason = "policy_denied"
    return {
        "decision": decision,
        "reason": reason,
        "approval_policy": (
            normalization_service.normalize_approval_policy(approval_policy)
            if str(approval_policy or "").strip()
            else None
        ),
        "sandbox_mode": (
            normalization_service.normalize_sandbox_mode(sandbox_mode)
            if str(sandbox_mode or "").strip()
            else None
        ),
        "network_access_enabled": network_access_enabled if isinstance(network_access_enabled, bool) else None,
        "request_permission_enabled": (
            request_permission_enabled if isinstance(request_permission_enabled, bool) else None
        ),
    }


def shell_policy_contract_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    status = str(raw.get("status") or "").strip().lower()
    error_code = str(raw.get("error_code") or "").strip().lower()
    approval_id = str(raw.get("approval_id") or "").strip()
    explicit_decision = str(raw.get("policy_decision") or "").strip().lower()
    explicit_reason = str(raw.get("policy_decision_reason") or "").strip()
    requires_approval = bool(approval_id) or status in {
        "pending",
        "pending_approval",
        "approval_required",
    }
    blocked = bool(raw.get("allowed") is False) or status in {
        "policy_denied",
        "blocked",
        "denied",
        "invalid",
        "missing",
    }
    if explicit_decision in SHELL_POLICY_DECISIONS:
        decision = explicit_decision
        reason = explicit_reason or ("approval_required" if decision == "requires_approval" else "policy_allowed")
        if decision == "blocked" and not explicit_reason:
            reason = "policy_denied"
    else:
        blocked_reason = ""
        if blocked:
            blocked_reason = "policy_denied"
            if error_code:
                blocked_reason = f"{blocked_reason}:{error_code}"
        inferred = shell_policy_decision_contract(
            approval_policy=str(raw.get("approval_policy") or "").strip() or None,
            sandbox_mode=str(raw.get("sandbox_mode") or "").strip() or None,
            network_access_enabled=normalization_service.optional_bool(raw.get("network_access_enabled")),
            request_permission_enabled=normalization_service.optional_bool(raw.get("request_permission_enabled")),
            requires_approval=requires_approval,
            blocked=blocked,
            blocked_reason=blocked_reason or None,
        )
        decision = str(inferred["decision"])
        reason = str(inferred["reason"])
    return shell_policy_decision_contract(
        approval_policy=str(raw.get("approval_policy") or "").strip() or None,
        sandbox_mode=str(raw.get("sandbox_mode") or "").strip() or None,
        network_access_enabled=normalization_service.optional_bool(raw.get("network_access_enabled")),
        request_permission_enabled=normalization_service.optional_bool(raw.get("request_permission_enabled")),
        requires_approval=(decision == "requires_approval"),
        blocked=(decision == "blocked"),
        blocked_reason=reason if decision == "blocked" else None,
    )


def runtime_policy_status_payload(
    *,
    approval_policy: str,
    sandbox_mode: str,
    web_search_mode: str,
    network_access_enabled: bool,
) -> dict[str, str]:
    return {
        "approval_policy": approval_policy,
        "sandbox_mode": sandbox_mode,
        "web_search_mode": web_search_mode,
        "network_access": normalization_service.network_access_label(network_access_enabled),
    }


def runtime_policy_status_with_permission_mode_payload(
    *,
    approval_policy: str,
    sandbox_mode: str,
    web_search_mode: str,
    network_access_enabled: bool,
) -> dict[str, str]:
    status = runtime_policy_status_payload(
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        web_search_mode=web_search_mode,
        network_access_enabled=network_access_enabled,
    )
    status["permission_mode"] = normalization_service.permission_mode_label(
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        network_access_enabled=network_access_enabled,
    )
    return status
