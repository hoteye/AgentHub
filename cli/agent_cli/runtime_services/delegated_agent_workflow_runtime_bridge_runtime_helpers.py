from __future__ import annotations

from typing import Any, Callable, Dict


def delegated_result_state_metrics_impl(
    runtime: Any,
    *,
    delegated_result_status_fn: Callable[[Any], str],
    delegated_completion_policy_fn: Callable[..., str],
    delegated_completion_state_fn: Callable[..., str],
    delegated_result_state_fn: Callable[..., str],
) -> Dict[str, int]:
    metrics: Dict[str, int] = {
        "delegated_result_returned": 0,
        "delegated_result_adopted": 0,
        "delegated_result_pending_review": 0,
        "background_result_returned": 0,
        "background_result_adopted": 0,
        "background_result_pending_review": 0,
    }
    sessions = list(getattr(runtime, "_delegated_agents", {}).values())
    for session in sessions:
        with session.condition:
            status = delegated_result_status_fn(session)
            completion_policy = delegated_completion_policy_fn(
                role=getattr(session, "role", ""),
                delegation_mode=getattr(session, "delegation_mode", ""),
                wait_required=getattr(session, "wait_required", None),
            )
            completion_state = delegated_completion_state_fn(
                status=status,
                adopted=bool(getattr(session, "adopted", False)),
                completion_policy=completion_policy,
            )
            result_state = delegated_result_state_fn(
                status=status,
                completion_state=completion_state,
                adopted=bool(getattr(session, "adopted", False)),
            )
            delegation_mode = str(getattr(session, "delegation_mode", "") or "").strip().lower()
        if result_state == "returned":
            metrics["delegated_result_returned"] += 1
            if delegation_mode == "background":
                metrics["background_result_returned"] += 1
        elif result_state == "adopted":
            metrics["delegated_result_adopted"] += 1
            if delegation_mode == "background":
                metrics["background_result_adopted"] += 1
        elif result_state == "pending_review":
            metrics["delegated_result_pending_review"] += 1
            if delegation_mode == "background":
                metrics["background_result_pending_review"] += 1
    return metrics


def delegated_terminal_state_impl(
    *,
    status: Any,
    terminal_reason: Any,
    has_text: bool,
) -> str:
    normalized_status = str(status or "").strip().lower()
    normalized_reason = str(terminal_reason or "").strip().lower()
    if normalized_reason in {"orphan_cleanup", "restore_resolution_failed", "role_override_changed"}:
        return "orphaned"
    if normalized_reason == "close_requested":
        return "closed_by_request"
    if normalized_status == "failed" or normalized_reason == "failed":
        return "failed"
    if normalized_status == "completed" or normalized_reason == "completed":
        return "completed"
    if normalized_status == "closed":
        return "completed" if has_text else "cancelled"
    if normalized_status == "cancelled":
        return "cancelled"
    return ""
