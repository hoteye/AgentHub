from __future__ import annotations

from typing import Any


_PENDING_REVIEW_COMPLETION_STATES = {"ready_to_adopt", "awaiting_join", "pending_review"}
_PENDING_REVIEW_NEXT_ACTIONS = {
    "review_or_adopt_teammate_result",
    "wait_agent_to_adopt",
    "manual_review_required",
}
_BLOCKED_NEXT_ACTIONS = {
    "failure_observed",
    "inspect_error_or_retry",
    "inspect_or_retry_empty_result",
    "execution_failed",
    "execution_failed_with_blockers",
    "execution_timed_out",
    "execution_cancelled",
}
_ADOPTED_NEXT_ACTIONS = {"already_adopted"}


def selector_value(value: Any) -> str:
    text = str(value or "").strip()
    if text in {"", "-", "inherit"}:
        return ""
    return text


def normalize_join_result_state(
    *,
    terminal_status: Any,
    explicit_state: Any = "",
    completion_state: Any = "",
    next_action: Any = "",
    adopted: bool = False,
    final_apply_state: Any = "",
    final_apply_pending: bool = False,
    notification_state: Any = "",
) -> str:
    normalized_terminal = selector_value(terminal_status).lower()
    normalized_explicit = selector_value(explicit_state).lower()
    normalized_completion = selector_value(completion_state).lower()
    normalized_action = selector_value(next_action).lower()
    normalized_apply_state = selector_value(final_apply_state).lower()
    normalized_notification = selector_value(notification_state).lower()

    blocked = (
        normalized_explicit == "blocked"
        or normalized_apply_state in {"blocked", "rejected"}
        or normalized_action in _BLOCKED_NEXT_ACTIONS
        or normalized_terminal in {"failed", "timed_out", "cancelled"}
    )
    pending_review = (
        normalized_explicit == "pending_review"
        or bool(final_apply_pending)
        or normalized_apply_state == "pending"
        or normalized_completion in _PENDING_REVIEW_COMPLETION_STATES
        or normalized_action in _PENDING_REVIEW_NEXT_ACTIONS
    )
    adopted_signal = (
        normalized_explicit == "adopted"
        or bool(adopted)
        or normalized_completion == "adopted"
        or normalized_action in _ADOPTED_NEXT_ACTIONS
        or normalized_notification == "foreground_adopted"
        or normalized_apply_state == "applied"
    )
    returned_signal = normalized_explicit == "returned" or normalized_terminal == "completed"

    # Guardrail: blocked/pending states win over adopted to avoid false "adopted" projection.
    if blocked:
        return "blocked"
    if pending_review:
        return "pending_review"
    if adopted_signal:
        return "adopted"
    if returned_signal:
        return "returned"
    return "pending"


def normalize_join_next_action(
    *,
    next_action: Any,
    result_state: str,
    completion_state: Any = "",
) -> str:
    normalized_action = selector_value(next_action)
    if normalized_action:
        return normalized_action
    normalized_completion = selector_value(completion_state).lower()
    normalized_state = selector_value(result_state).lower()
    if normalized_state == "adopted":
        return "already_adopted"
    if normalized_state == "pending_review":
        if normalized_completion == "ready_to_adopt":
            return "review_or_adopt_teammate_result"
        if normalized_completion == "awaiting_join":
            return "wait_agent_to_adopt"
        return "manual_review_required"
    if normalized_state == "returned":
        return "result_returned"
    if normalized_state == "blocked":
        return "manual_review_required"
    return ""


def normalize_join_summary(
    *,
    summary: Any,
    result_state: str,
    terminal_status: Any,
) -> str:
    normalized_summary = selector_value(summary)
    normalized_terminal = selector_value(terminal_status).lower()
    normalized_state = selector_value(result_state).lower()
    if normalized_summary and normalized_summary.lower() not in {
        "",
        normalized_terminal,
        "completed",
        "failed",
        "timed_out",
        "cancelled",
    }:
        return normalized_summary
    if normalized_state == "adopted":
        return "adopted"
    if normalized_state == "pending_review":
        return "awaiting operator review"
    if normalized_state == "returned":
        return "returned to orchestrator"
    if normalized_state == "blocked":
        return "blocked pending review"
    if normalized_summary:
        return normalized_summary
    if normalized_terminal:
        return normalized_terminal
    return "pending"
