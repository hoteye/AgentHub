from __future__ import annotations

from typing import Any

from cli.agent_cli import runtime_policy_normalization_helpers_runtime as normalization_service
from cli.agent_cli.runtime_exec_policy_bridge import (
    exec_approval_requirement_for_decision,
    exec_approval_requirement_to_dict,
)
from cli.agent_cli.runtime_exec_policy_models import (
    CommandApprovalDecision,
    CommandApprovalDecisionValue,
)

EXEC_APPROVAL_REQUIREMENTS = ("skip", "needs_approval", "forbidden")


def _normalized_segments_from_evidence(evidence: dict[str, Any]) -> list[str]:
    segments: list[str] = []
    for change in list(evidence.get("changes") or []):
        if not isinstance(change, dict):
            continue
        path = str(change.get("path") or "").strip()
        if path and path not in segments:
            segments.append(path)
    if segments:
        return segments
    file_path = str(evidence.get("file_path") or "").strip()
    if file_path:
        return [file_path]
    request_kind = str(evidence.get("request_kind") or "").strip()
    if request_kind:
        return [request_kind]
    function_call_name = str(evidence.get("function_call_name") or "").strip()
    if function_call_name:
        return [function_call_name]
    return ["apply_patch"]


def evaluate_apply_patch_decision(
    *,
    approval_policy: str | None,
    sandbox_mode: str | None,
    evidence: dict[str, Any] | None = None,
    preview_error: str | None = None,
) -> CommandApprovalDecision:
    normalized_approval_policy = normalization_service.normalize_approval_policy(
        approval_policy,
        default="on-request",
    )
    normalized_sandbox_mode = normalization_service.normalize_sandbox_mode(
        sandbox_mode,
        default="workspace-write",
    )
    structured_evidence = dict(evidence or {})
    resolved_preview_error = (
        str(preview_error or structured_evidence.get("preview_error") or "").strip() or None
    )
    structured_evidence.setdefault("preview_ok", resolved_preview_error is None)
    if resolved_preview_error:
        structured_evidence["preview_error"] = resolved_preview_error

    if normalized_sandbox_mode == "read-only":
        decision = CommandApprovalDecisionValue.FORBIDDEN
        reason_code = "apply_patch_sandbox_read_only"
        reason_text = "Patch execution is forbidden while the runtime sandbox is read-only."
        source = "sandbox_requirement"
    elif resolved_preview_error:
        decision = CommandApprovalDecisionValue.FORBIDDEN
        reason_code = "apply_patch_preview_invalid"
        reason_text = f"Patch preview failed ({resolved_preview_error}); patch execution is forbidden."
        source = "preview_validation"
    elif normalized_approval_policy == "never":
        decision = CommandApprovalDecisionValue.ALLOW
        reason_code = "apply_patch_allowed"
        reason_text = "Runtime policy allows the patch to run without prior approval."
        source = "policy_axis"
    else:
        decision = CommandApprovalDecisionValue.PROMPT
        reason_code = "apply_patch_approval_required"
        reason_text = "Runtime policy requires approval before applying workspace patches."
        source = "policy_axis"
    return CommandApprovalDecision(
        decision=decision,
        reason_code=reason_code,
        reason_text=reason_text,
        matched_rules=(
            {
                "source": source,
                "rule_id": reason_code,
                "decision": decision.value,
                "evidence": structured_evidence,
            },
        ),
        proposed_rule=None,
        normalized_segments=_normalized_segments_from_evidence(structured_evidence),
    )


def evaluate_apply_patch_requirement(
    *,
    approval_policy: str | None,
    sandbox_mode: str | None,
    evidence: dict[str, Any] | None = None,
    preview_error: str | None = None,
) -> dict[str, Any]:
    normalized_approval_policy = normalization_service.normalize_approval_policy(
        approval_policy,
        default="on-request",
    )
    normalized_sandbox_mode = normalization_service.normalize_sandbox_mode(
        sandbox_mode,
        default="workspace-write",
    )
    structured_evidence = dict(evidence or {})
    resolved_preview_error = (
        str(preview_error or structured_evidence.get("preview_error") or "").strip() or None
    )
    structured_evidence.setdefault("preview_ok", resolved_preview_error is None)
    if resolved_preview_error:
        structured_evidence["preview_error"] = resolved_preview_error
    decision = evaluate_apply_patch_decision(
        approval_policy=normalized_approval_policy,
        sandbox_mode=normalized_sandbox_mode,
        evidence=structured_evidence,
        preview_error=resolved_preview_error,
    )
    requirement_payload = exec_approval_requirement_to_dict(
        exec_approval_requirement_for_decision(decision)
    )

    return {
        **requirement_payload,
        **decision.to_dict(),
        "approval_policy": normalized_approval_policy,
        "sandbox_mode": normalized_sandbox_mode,
        "evidence": structured_evidence,
    }


__all__ = [
    "EXEC_APPROVAL_REQUIREMENTS",
    "evaluate_apply_patch_decision",
    "evaluate_apply_patch_requirement",
]
