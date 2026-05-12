from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli import (
    runtime_codex_headless_contract_runtime as codex_headless_contract_runtime_service,
)
from cli.agent_cli import runtime_exec_policy_apply_patch as apply_patch_policy_runtime
from cli.agent_cli import (
    runtime_policy_normalization_helpers_runtime as normalization_service,
)
from cli.agent_cli.runtime_exec_policy_bridge import (
    exec_approval_requirement_for_decision,
    exec_approval_requirement_to_dict,
)
from cli.agent_cli.runtime_exec_policy_classification import classify_exec_command
from cli.agent_cli.runtime_exec_policy_models import (
    CommandApprovalDecision,
    CommandApprovalDecisionValue,
)
from cli.agent_cli.runtime_exec_policy_rules import load_runtime_exec_policy_rules
from cli.agent_cli.tools_core import apply_patch_bridge


def runtime_policy_axes(runtime: Any) -> dict[str, Any]:
    status: dict[str, Any] = {}
    status_getter = getattr(runtime, "runtime_policy_status", None)
    if callable(status_getter):
        try:
            status = dict(status_getter() or {})
        except Exception:
            status = {}
    runtime_policy = getattr(runtime, "runtime_policy", None)
    approval_policy = (
        str(status.get("approval_policy") or "").strip()
        or str(getattr(runtime_policy, "approval_policy", "") or "").strip()
    )
    sandbox_mode = (
        str(status.get("sandbox_mode") or "").strip()
        or str(getattr(runtime_policy, "sandbox_mode", "") or "").strip()
    )
    if not approval_policy:
        legacy_requires_approval = getattr(runtime, "patch_requires_approval", None)
        if callable(legacy_requires_approval):
            try:
                approval_policy = "on-request" if bool(legacy_requires_approval()) else "never"
            except Exception:
                approval_policy = ""
    if not sandbox_mode:
        legacy_read_only = getattr(runtime, "workspace_is_read_only", None)
        if callable(legacy_read_only):
            try:
                sandbox_mode = "read-only" if bool(legacy_read_only()) else "workspace-write"
            except Exception:
                sandbox_mode = ""
    normalized_approval_policy = normalization_service.normalize_approval_policy(
        approval_policy,
        default="on-request",
    )
    normalized_sandbox_mode = normalization_service.normalize_sandbox_mode(
        sandbox_mode,
        default="workspace-write",
    )
    raw_network_access = status.get("network_access_enabled")
    if raw_network_access is None:
        raw_network_access = status.get("network_access")
    if raw_network_access is None:
        raw_network_access = getattr(runtime_policy, "network_access_enabled", None)
    normalized_network_access_enabled = normalization_service.normalize_network_access(
        raw_network_access,
        default=True,
    )
    effective_policy = codex_headless_contract_runtime_service.effective_model_runtime_policy(
        runtime,
        approval_policy=normalized_approval_policy,
        sandbox_mode=normalized_sandbox_mode,
    )
    effective_policy["network_access_enabled"] = normalized_network_access_enabled
    return effective_policy


def _requested_network_access(additional_permissions: dict[str, Any] | None) -> bool:
    if not isinstance(additional_permissions, dict):
        return False
    network = additional_permissions.get("network")
    if isinstance(network, dict):
        return normalization_service.optional_bool(network.get("enabled")) is True
    return normalization_service.optional_bool(network) is True


def resolve_runtime_policy_cwd(runtime: Any, *, workdir: str | None = None) -> Path:
    candidate = str(workdir or "").strip()
    if candidate:
        path = Path(candidate)
        if not path.is_absolute():
            base = Path(str(getattr(runtime, "cwd", "") or "")).expanduser()
            path = (base if str(base) else Path.cwd()) / path
    else:
        base = str(getattr(runtime, "cwd", "") or "").strip()
        path = Path(base).expanduser() if base else Path.cwd()
    try:
        return path.resolve()
    except OSError:
        return path


def _policy_decision_pair(*, requirement_name: str, reason_code: str | None) -> tuple[str, str]:
    normalized_requirement = str(requirement_name or "").strip().lower()
    normalized_reason_code = str(reason_code or "").strip()
    if normalized_requirement == "needs_approval":
        return ("requires_approval", "approval_required")
    if normalized_requirement == "forbidden":
        if normalized_reason_code:
            return ("blocked", f"policy_denied:{normalized_reason_code}")
        return ("blocked", "policy_denied")
    return ("allowed", "policy_allowed")


def _noninteractive_claude_denial_payload(
    *,
    reason_code: str,
    reason_text: str,
) -> dict[str, Any]:
    denial_text = (
        codex_headless_contract_runtime_service.claude_noninteractive_approval_denial_text(
            reason_text=reason_text,
        )
    )
    return {
        "reason_code": reason_code,
        "reason_text": denial_text,
        "error": denial_text,
        "output_text": denial_text,
        "stderr": denial_text,
        "function_call_output": denial_text,
        "function_call_output_model_visible": True,
    }


def evaluate_exec_command_runtime_policy(
    runtime: Any,
    command: str,
    *,
    workdir: str | None = None,
    sandbox_permissions: str | None = None,
    additional_permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    axes = runtime_policy_axes(runtime)
    resolved_cwd = resolve_runtime_policy_cwd(runtime, workdir=workdir)
    rules = load_runtime_exec_policy_rules(cwd=resolved_cwd)
    requested_network_access = _requested_network_access(additional_permissions)
    decision = classify_exec_command(
        command,
        approval_policy=axes["approval_policy"],
        sandbox_mode=axes["sandbox_mode"],
        network_access_enabled=axes["network_access_enabled"],
        network_access_requested=requested_network_access,
        rules=rules,
    )
    requirement = exec_approval_requirement_for_decision(decision)
    decision_payload = decision.to_dict()
    requirement_payload = exec_approval_requirement_to_dict(requirement)
    if (
        bool(axes.get("claude_noninteractive_headless"))
        and str(requirement_payload.get("requirement") or "").strip() == "needs_approval"
    ):
        decision_payload = {
            **decision_payload,
            "decision": CommandApprovalDecisionValue.FORBIDDEN.value,
            **_noninteractive_claude_denial_payload(
                reason_code=str(decision_payload.get("reason_code") or "approval_required"),
                reason_text=str(decision_payload.get("reason_text") or ""),
            ),
        }
        decision = CommandApprovalDecision.from_dict(decision_payload)
        requirement = exec_approval_requirement_for_decision(decision)
        requirement_payload = exec_approval_requirement_to_dict(requirement)
    if (
        bool(axes.get("codex_noninteractive_headless"))
        and str(requirement_payload.get("requirement") or "").strip() == "forbidden"
    ):
        decision_payload["reason_text"] = (
            codex_headless_contract_runtime_service.codex_noninteractive_exec_denial_text(
                sandbox_mode=axes["sandbox_mode"],
                reason_code=str(decision_payload.get("reason_code") or ""),
                reason_text=str(decision_payload.get("reason_text") or ""),
            )
        )
        decision = CommandApprovalDecision.from_dict(decision_payload)
        requirement = exec_approval_requirement_for_decision(decision)
        requirement_payload = exec_approval_requirement_to_dict(requirement)
    policy_decision, policy_decision_reason = _policy_decision_pair(
        requirement_name=str(requirement_payload.get("requirement") or ""),
        reason_code=str(decision_payload.get("reason_code") or ""),
    )
    denial_text = str(decision_payload.get("reason_text") or "").strip()
    return {
        "approval_policy": axes["approval_policy"],
        "sandbox_mode": axes["sandbox_mode"],
        "decision": decision,
        "decision_payload": decision_payload,
        "requirement": requirement,
        "requirement_payload": requirement_payload,
        "policy_decision": policy_decision,
        "policy_decision_reason": policy_decision_reason,
        "payload": {
            "approval_policy": axes["approval_policy"],
            "sandbox_mode": axes["sandbox_mode"],
            "network_access_enabled": bool(axes["network_access_enabled"]),
            "codex_noninteractive_headless": bool(axes.get("codex_noninteractive_headless")),
            "claude_noninteractive_headless": bool(axes.get("claude_noninteractive_headless")),
            "policy_decision": policy_decision,
            "policy_decision_reason": policy_decision_reason,
            "reason_code": str(decision_payload.get("reason_code") or ""),
            "reason_text": denial_text,
            "matched_rules": list(decision_payload.get("matched_rules") or []),
            "proposed_rule": decision_payload.get("proposed_rule"),
            "normalized_segments": list(decision_payload.get("normalized_segments") or []),
            "command_approval": decision_payload,
            "exec_approval_requirement": requirement_payload,
            **(
                {"requested_sandbox_permissions": str(sandbox_permissions or "").strip()}
                if str(sandbox_permissions or "").strip()
                else {}
            ),
            **(
                {"requested_additional_permissions": dict(additional_permissions)}
                if isinstance(additional_permissions, dict)
                else {}
            ),
            **({"requested_network_access": True} if requested_network_access else {}),
            **(
                {
                    "output_text": denial_text,
                    "stderr": denial_text,
                    "function_call_output": denial_text,
                    "function_call_output_model_visible": True,
                }
                if str(requirement_payload.get("requirement") or "").strip() == "forbidden"
                and denial_text
                else {}
            ),
        },
    }


def evaluate_apply_patch_runtime_policy(
    runtime: Any,
    *,
    patch_text: str,
    workspace_root: Path,
) -> dict[str, Any]:
    axes = runtime_policy_axes(runtime)
    if axes["sandbox_mode"] == "read-only":
        decision = apply_patch_policy_runtime.evaluate_apply_patch_decision(
            approval_policy=axes["approval_policy"],
            sandbox_mode=axes["sandbox_mode"],
            evidence={},
        )
        requirement_payload = {
            **exec_approval_requirement_to_dict(exec_approval_requirement_for_decision(decision)),
            **decision.to_dict(),
            "approval_policy": axes["approval_policy"],
            "sandbox_mode": axes["sandbox_mode"],
            "evidence": {},
        }
    elif axes["approval_policy"] == "never":
        decision = apply_patch_policy_runtime.evaluate_apply_patch_decision(
            approval_policy=axes["approval_policy"],
            sandbox_mode=axes["sandbox_mode"],
            evidence={},
        )
        requirement_payload = {
            **exec_approval_requirement_to_dict(exec_approval_requirement_for_decision(decision)),
            **decision.to_dict(),
            "approval_policy": axes["approval_policy"],
            "sandbox_mode": axes["sandbox_mode"],
            "evidence": {},
        }
    else:
        requirement_payload = apply_patch_bridge.evaluate_apply_patch_requirement(
            patch_text=patch_text,
            workspace_root=workspace_root,
            approval_policy=axes["approval_policy"],
            sandbox_mode=axes["sandbox_mode"],
        )
    if (
        bool(axes.get("codex_noninteractive_headless"))
        and str(requirement_payload.get("requirement") or "").strip() == "forbidden"
    ):
        denial_text = (
            codex_headless_contract_runtime_service.codex_noninteractive_apply_patch_denial_text(
                sandbox_mode=axes["sandbox_mode"],
                reason_code=str(requirement_payload.get("reason_code") or ""),
                reason_text=str(requirement_payload.get("reason_text") or ""),
            )
        )
        requirement_payload = {
            **dict(requirement_payload),
            "reason_text": denial_text,
            "error": denial_text,
            "function_call_output": denial_text,
            "function_call_output_model_visible": bool(denial_text),
        }
    if (
        bool(axes.get("claude_noninteractive_headless"))
        and str(requirement_payload.get("requirement") or "").strip() == "needs_approval"
    ):
        denial_payload = _noninteractive_claude_denial_payload(
            reason_code=str(requirement_payload.get("reason_code") or "approval_required"),
            reason_text=str(requirement_payload.get("reason_text") or ""),
        )
        requirement_payload = {
            **dict(requirement_payload),
            "requirement": "forbidden",
            "decision": CommandApprovalDecisionValue.FORBIDDEN.value,
            **denial_payload,
        }
    policy_decision, policy_decision_reason = _policy_decision_pair(
        requirement_name=str(requirement_payload.get("requirement") or ""),
        reason_code=str(requirement_payload.get("reason_code") or ""),
    )
    return {
        "approval_policy": axes["approval_policy"],
        "sandbox_mode": axes["sandbox_mode"],
        "requirement_payload": requirement_payload,
        "policy_decision": policy_decision,
        "policy_decision_reason": policy_decision_reason,
        "payload": {
            "approval_policy": axes["approval_policy"],
            "sandbox_mode": axes["sandbox_mode"],
            "codex_noninteractive_headless": bool(axes.get("codex_noninteractive_headless")),
            "claude_noninteractive_headless": bool(axes.get("claude_noninteractive_headless")),
            "policy_decision": policy_decision,
            "policy_decision_reason": policy_decision_reason,
            "reason_code": str(requirement_payload.get("reason_code") or ""),
            "reason_text": str(requirement_payload.get("reason_text") or ""),
            "matched_rules": list(requirement_payload.get("matched_rules") or []),
            "proposed_rule": requirement_payload.get("proposed_rule"),
            "normalized_segments": list(requirement_payload.get("normalized_segments") or []),
            "exec_approval_requirement": {
                "requirement": str(requirement_payload.get("requirement") or "").strip()
            },
            "apply_patch_requirement": dict(requirement_payload),
            **(
                {
                    "error": str(requirement_payload.get("error") or ""),
                    "function_call_output": requirement_payload.get("function_call_output"),
                    "function_call_output_model_visible": bool(
                        requirement_payload.get("function_call_output_model_visible")
                    ),
                }
                if str(requirement_payload.get("requirement") or "").strip() == "forbidden"
                else {}
            ),
        },
    }


__all__ = [
    "evaluate_apply_patch_runtime_policy",
    "evaluate_exec_command_runtime_policy",
    "resolve_runtime_policy_cwd",
    "runtime_policy_axes",
]
