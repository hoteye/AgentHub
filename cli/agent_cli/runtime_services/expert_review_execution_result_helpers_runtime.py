from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable

from cli.agent_cli.models import CommandExecutionResult, ToolEvent


def expert_review_tool_payload(
    *,
    result: Mapping[str, Any],
    request_payload: Mapping[str, Any],
    gate_payload: Mapping[str, Any],
    selection: Mapping[str, Any],
    child_agent_id: str,
    candidate_provider_display_fn: Callable[[Mapping[str, Any]], str],
    candidate_model_display_fn: Callable[[Mapping[str, Any]], str],
    candidate_model_selector_fn: Callable[[Mapping[str, Any]], str | None],
    normalized_text_fn: Callable[[Any], str],
) -> dict[str, Any]:
    selected_candidate = dict(selection.get("selected_candidate") or {})
    selection_policy = dict(selection.get("policy") or {})
    return {
        "ok": str(result.get("status") or "").strip().lower() == "ok",
        "tool_family": "expert_review",
        "status": result.get("status"),
        "summary": result.get("summary"),
        "structured_payload": dict(result.get("structured_payload") or {}),
        "request": dict(request_payload or {}),
        "reviewer_selection": {
            "selection_reason": str(selection.get("selection_reason") or ""),
            "same_vendor_fallback_used": bool(selection.get("same_vendor_fallback_used")),
            "provider": candidate_provider_display_fn(selected_candidate),
            "config_provider_name": normalized_text_fn(selected_candidate.get("config_provider_name")),
            "model": candidate_model_display_fn(selected_candidate),
            "model_selector": candidate_model_selector_fn(selected_candidate) or "",
            "cross_vendor": bool(selected_candidate.get("cross_vendor")),
            "selection_bucket": normalized_text_fn(selected_candidate.get("selection_bucket")),
            "reviewer_capability_policy": normalized_text_fn(
                selected_candidate.get("reviewer_capability_policy")
                or selection_policy.get("reviewer_capability_policy")
            ),
            "reviewer_capability_source": normalized_text_fn(
                selected_candidate.get("reviewer_capability_source")
                or selected_candidate.get("reviewer_capability_policy_source")
                or selection_policy.get("reviewer_capability_policy_source")
            ),
            "reviewer_reasoning_strategy": normalized_text_fn(
                selected_candidate.get("reviewer_reasoning_strategy")
            ),
            "reviewer_reasoning_effort": normalized_text_fn(
                selected_candidate.get("reviewer_reasoning_effort")
            ),
            "reviewer_reasoning_mode": normalized_text_fn(
                selected_candidate.get("reviewer_reasoning_mode")
            ),
            "reviewer_selection_tier": normalized_text_fn(
                selected_candidate.get("reviewer_selection_tier")
            ),
            "reasoning_capability_validation": normalized_text_fn(
                selected_candidate.get("reasoning_capability_validation")
                or selection_policy.get("reasoning_capability_validation")
            ),
            "reasoning_capability_check_performed": bool(
                selected_candidate.get(
                    "reasoning_capability_check_performed",
                    selection_policy.get("reasoning_capability_check_performed"),
                )
            ),
            "reasoning_capability_warning_present": bool(
                selected_candidate.get(
                    "reasoning_capability_warning_present",
                    selection_policy.get("reasoning_capability_warning_present"),
                )
            ),
            "reasoning_capability_warning": normalized_text_fn(
                selected_candidate.get("reasoning_capability_warning")
                or selection_policy.get("reasoning_capability_warning")
            ),
        },
        "gate": dict(gate_payload or {}),
        "child_agent_id": child_agent_id or "",
    }


def expert_review_assistant_text(
    result: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
    reviewer_identity_fn: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> str:
    summary = normalized_text_fn(result.get("summary"))
    payload = dict(result.get("structured_payload") or {})
    reviewer = reviewer_identity_fn(payload)
    if str(result.get("status") or "").strip().lower() == "ok":
        lines = [summary or "Expert review completed."]
        verdict = normalized_text_fn(payload.get("verdict"))
        confidence = normalized_text_fn(payload.get("confidence"))
        finding_count = payload.get("finding_count")
        reviewer_provider = normalized_text_fn(reviewer.get("provider"))
        reviewer_model = normalized_text_fn(reviewer.get("model"))
        recommended_action = normalized_text_fn(payload.get("recommended_action"))
        if verdict:
            lines.append(f"verdict={verdict}")
        if confidence:
            lines.append(f"confidence={confidence}")
        if finding_count not in (None, ""):
            lines.append(f"findings={finding_count}")
        if reviewer_provider or reviewer_model:
            lines.append(f"reviewer={reviewer_provider} | {reviewer_model}".strip(" |"))
        if recommended_action:
            lines.append(f"recommended_action={recommended_action}")
        return "\n".join(lines)
    lines = [summary or "Expert review failed."]
    error_code = normalized_text_fn(payload.get("error_code"))
    stage = normalized_text_fn(payload.get("stage"))
    detail = normalized_text_fn(payload.get("detail"))
    if error_code:
        lines.append(f"error_code={error_code}")
    if stage:
        lines.append(f"stage={stage}")
    if detail:
        lines.append(f"detail={detail}")
    return "\n".join(lines)


def expert_review_command_result(
    *,
    result: Mapping[str, Any],
    request_payload: Mapping[str, Any],
    gate_payload: Mapping[str, Any],
    selection: Mapping[str, Any],
    item_events: Sequence[Mapping[str, Any]],
    child_agent_id: str,
    expert_review_tool_payload_fn: Callable[..., dict[str, Any]],
    normalized_text_fn: Callable[[Any], str],
    expert_review_assistant_text_fn: Callable[[Mapping[str, Any]], str],
) -> CommandExecutionResult:
    payload = expert_review_tool_payload_fn(
        result=result,
        request_payload=request_payload,
        gate_payload=gate_payload,
        selection=selection,
        child_agent_id=child_agent_id,
    )
    event = ToolEvent(
        name="expert_review",
        ok=bool(payload.get("ok")),
        summary=normalized_text_fn(result.get("summary")) or "expert_review completed",
        payload=payload,
    )
    return CommandExecutionResult(
        assistant_text=expert_review_assistant_text_fn(result),
        tool_events=[event],
        item_events=[dict(item) for item in list(item_events or []) if isinstance(item, Mapping)],
    )


__all__ = [
    "expert_review_assistant_text",
    "expert_review_command_result",
    "expert_review_tool_payload",
]
