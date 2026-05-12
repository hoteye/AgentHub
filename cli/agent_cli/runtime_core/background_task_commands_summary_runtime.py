from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.runtime_core import (
    background_task_commands_summary_runtime_state_helpers as _state_helpers,
)


_BOOL_TRUE = {"1", "true", "yes", "on"}
_PENDING_REVIEW_NEXT_ACTIONS = {
    "manual_review_required",
    "review_or_adopt_teammate_result",
    "wait_agent_to_adopt",
}
_BLOCKED_NEXT_ACTIONS = {
    "execution_cancelled",
    "execution_failed",
    "execution_failed_with_blockers",
    "execution_timed_out",
    "failure_observed",
    "inspect_error_or_retry",
    "inspect_or_retry_empty_result",
}
_ADOPTED_NEXT_ACTIONS = {"already_adopted"}
_PENDING_REVIEW_COMPLETION_STATES = {"awaiting_join", "pending_review"}


def parse_background_teammate_args(
    raw_args: str,
    *,
    runtime_cwd: Any,
    parse_option_tokens_fn: Callable[..., tuple[list[str], dict[str, str]]],
    parse_csv_paths_fn: Callable[[Any], list[str]],
    parse_positive_float_fn: Callable[..., float],
) -> dict[str, Any]:
    positionals, options = parse_option_tokens_fn(
        raw_args,
        value_flags={
            "--provider",
            "--model",
            "--reasoning-effort",
            "--cwd",
            "--approval-policy",
            "--sandbox-mode",
            "--allowed-paths",
            "--blocked-paths",
            "--timeout-seconds",
        },
    )
    task_text = " ".join(positionals).strip()
    if not task_text:
        raise ValueError("background teammate requires a task prompt")
    provider = str(options.get("provider") or "").strip()
    model = str(options.get("model") or "").strip()
    reasoning_effort = str(options.get("reasoning-effort") or "").strip()
    task_cwd = str(options.get("cwd") or runtime_cwd or "").strip()
    approval_policy = str(options.get("approval-policy") or "never").strip() or "never"
    sandbox_mode = str(options.get("sandbox-mode") or "read-only").strip() or "read-only"
    allowed_paths = parse_csv_paths_fn(options.get("allowed-paths"))
    blocked_paths = parse_csv_paths_fn(options.get("blocked-paths"))
    timeout_text = str(options.get("timeout-seconds") or "").strip()
    timeout_payload: dict[str, Any] = {}
    if timeout_text:
        timeout_payload["timeout_seconds"] = parse_positive_float_fn(
            timeout_text,
            option_name="--timeout-seconds",
        )
    return {
        "task_text": task_text,
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "task_cwd": task_cwd,
        "approval_policy": approval_policy,
        "sandbox_mode": sandbox_mode,
        "allowed_paths": allowed_paths,
        "blocked_paths": blocked_paths,
        "timeout_payload": timeout_payload,
    }


def background_teammate_approval_kwargs(
    parsed: dict[str, Any],
    *,
    queue_cwd: str,
) -> dict[str, Any]:
    return {
        "requested_by": "cli",
        "provider": str(parsed["provider"]),
        "model": str(parsed["model"]),
        "reasoning_effort": str(parsed["reasoning_effort"]),
        "task_cwd": str(parsed["task_cwd"]),
        "queue_cwd": queue_cwd,
        "approval_policy": str(parsed["approval_policy"]),
        "sandbox_mode": str(parsed["sandbox_mode"]),
        "allowed_paths": list(parsed["allowed_paths"]),
        "blocked_paths": list(parsed["blocked_paths"]),
        "timeout_seconds": dict(parsed["timeout_payload"]).get("timeout_seconds"),
    }


def background_teammate_enqueue_payload(parsed: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    provider = str(parsed["provider"])
    model = str(parsed["model"])
    reasoning_effort = str(parsed["reasoning_effort"])
    payload = {
        "task": str(parsed["task_text"]),
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "cwd": str(parsed["task_cwd"]),
        "approval_policy": str(parsed["approval_policy"]),
        "sandbox_mode": str(parsed["sandbox_mode"]),
        "allowed_paths": list(parsed["allowed_paths"]),
        "blocked_paths": list(parsed["blocked_paths"]),
        **dict(parsed["timeout_payload"]),
    }
    metadata = {
        "reason": "slash_command",
        "provider_name": provider,
        "model": model,
        "extra": {"reasoning_effort": reasoning_effort},
    }
    return payload, metadata


def background_tasks_text(
    *,
    item_count: int,
    enabled: bool,
    provider: str,
    queue_provider_label: str,
    worker_payload: dict[str, Any] | None,
    item_lines: list[str],
) -> str:
    lines = [f"background_tasks={item_count}"]
    lines.append(f"background_tasks_enabled={'true' if enabled else 'false'}")
    lines.append(f"background_tasks_provider={provider}")
    lines.append(f"background_tasks_queue={queue_provider_label}")
    payload = worker_payload or {}
    for key in ("health", "status", "mode"):
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"background_worker_{key}={value}")
    if payload.get("worker_pid") not in (None, "", 0):
        lines.append(f"background_worker_pid={payload['worker_pid']}")
    heartbeat = str(payload.get("last_heartbeat_at") or "").strip()
    if heartbeat:
        lines.append(f"background_worker_last_heartbeat_at={heartbeat}")
    if payload.get("last_cleanup_count") not in (None, "", 0):
        lines.append(f"background_worker_last_cleanup_count={payload['last_cleanup_count']}")
    returned_count, adopted_count, pending_review_count = _background_result_state_counts(item_lines)
    lines.append(f"background_result_returned={returned_count}")
    lines.append(f"background_result_adopted={adopted_count}")
    lines.append(f"background_result_pending_review={pending_review_count}")
    lines.extend(item_lines)
    return "\n".join(lines)


def workflows_text(
    *,
    delegated_lines: list[str],
    orchestration_lines: list[str],
    background_lines: list[str],
    orchestration_count: int,
    mirrored_count: int,
    background_enabled: bool,
    execution_projection_counts: dict[str, int] | None = None,
) -> str:
    lines = [f"workflows={len(delegated_lines) + len(orchestration_lines) + len(background_lines)}"]
    lines.append(f"delegated_workflows={len(delegated_lines)}")
    lines.append(f"orchestration_runs={max(0, int(orchestration_count))}")
    orchestration_ready, orchestration_running, orchestration_blocked, orchestration_review_pending = _orchestration_state_counts(
        orchestration_lines
    )
    lines.append(f"orchestration_ready={orchestration_ready}")
    lines.append(f"orchestration_running={orchestration_running}")
    lines.append(f"orchestration_blocked={orchestration_blocked}")
    lines.append(f"orchestration_review_pending={orchestration_review_pending}")
    lines.append(f"background_tasks={len(background_lines)}")
    lines.append(f"background_tasks_enabled={'true' if background_enabled else 'false'}")
    delegated_returned, delegated_adopted, delegated_pending_review = _delegated_result_state_counts(delegated_lines)
    background_returned, background_adopted, background_pending_review = _background_result_state_counts(background_lines)
    lines.append(f"delegated_result_returned={delegated_returned}")
    lines.append(f"delegated_result_adopted={delegated_adopted}")
    lines.append(f"delegated_result_pending_review={delegated_pending_review}")
    lines.append(f"background_result_returned={background_returned}")
    lines.append(f"background_result_adopted={background_adopted}")
    lines.append(f"background_result_pending_review={background_pending_review}")
    lines.append(
        "workflow_action_required="
        f"{int(orchestration_review_pending) + int(delegated_pending_review) + int(background_pending_review)}"
    )
    policy_denied_count, policy_rewrite_count, policy_checked_count = _workflow_policy_surface_counts(
        delegated_lines + orchestration_lines + background_lines
    )
    if policy_denied_count > 0:
        lines.append(f"workflow_policy_denied={policy_denied_count}")
    if policy_rewrite_count > 0:
        lines.append(f"workflow_policy_rewrite={policy_rewrite_count}")
    if policy_checked_count > 0:
        lines.append(f"workflow_policy_checked={policy_checked_count}")
    projection_counts = dict(execution_projection_counts or {})
    if projection_counts:
        projection_total = int(projection_counts.get("total", 0) or 0)
        projection_running = int(projection_counts.get("running", 0) or 0)
        projection_completed = int(projection_counts.get("completed", 0) or 0)
        projection_failed = int(projection_counts.get("failed", 0) or 0)
        projection_cancelled = int(projection_counts.get("cancelled", 0) or 0)
        projection_timed_out = int(projection_counts.get("timed_out", 0) or 0)
        projection_terminal = projection_completed + projection_failed + projection_cancelled + projection_timed_out
        projection_attention = projection_failed + projection_cancelled + projection_timed_out
        lines.append(f"execution_projection_runs={projection_total}")
        lines.append(f"execution_projection_running={projection_running}")
        lines.append(f"execution_projection_completed={projection_completed}")
        lines.append(f"execution_projection_failed={projection_failed}")
        lines.append(f"execution_projection_cancelled={projection_cancelled}")
        lines.append(f"execution_projection_timed_out={projection_timed_out}")
        lines.append(f"execution_projection_terminal={projection_terminal}")
        lines.append(f"execution_projection_attention={projection_attention}")
    if mirrored_count:
        lines.append(f"mirrored_background_tasks={mirrored_count}")
    lines.extend(delegated_lines)
    lines.extend(orchestration_lines)
    lines.extend(background_lines)
    return "\n".join(lines)


def execution_projection_counts(run_records: list[Any]) -> dict[str, int]:
    counts = {
        "total": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "timed_out": 0,
    }
    for item in list(run_records or []):
        raw_kind = getattr(item, "kind", None)
        if raw_kind is None and isinstance(item, dict):
            raw_kind = item.get("kind")
        raw_status = getattr(item, "status", None)
        if raw_status is None and isinstance(item, dict):
            raw_status = item.get("status")
        kind = str(getattr(raw_kind, "value", raw_kind) or "").strip().lower()
        status = str(getattr(raw_status, "value", raw_status) or "").strip().lower()
        if not kind or kind == "turn":
            continue
        counts["total"] += 1
        if status in counts:
            counts[status] += 1
    return counts


def _line_key_values(line: str) -> dict[str, str]:
    return _state_helpers.line_key_values(line)


def _line_pipe_parts(line: str) -> list[str]:
    return _state_helpers.line_pipe_parts(line)


def _delegated_result_state_counts(lines: list[str]) -> tuple[int, int, int]:
    return _state_helpers.delegated_result_state_counts(lines)


def _background_result_state_counts(lines: list[str]) -> tuple[int, int, int]:
    returned = 0
    adopted = 0
    pending_review = 0
    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line:
            continue
        values = _line_key_values(line)
        parts = _line_pipe_parts(line)
        state = _background_line_result_state(values, parts=parts)
        if state == "adopted":
            adopted += 1
            continue
        if state in {"blocked", "pending_review"}:
            pending_review += 1
            continue
        if state == "returned":
            returned += 1
    return returned, adopted, pending_review


def _background_line_result_state(values: dict[str, str], *, parts: list[str]) -> str:
    status = parts[2] if len(parts) > 2 else str(values.get("status") or "").strip().lower()
    terminal_state = str(values.get("terminal_state") or "").strip().lower() or status
    explicit_state = str(values.get("result_state") or "").strip().lower()
    completion_state = str(values.get("completion_state") or values.get("completion") or "").strip().lower()
    next_action = str(values.get("adoption_expectation") or values.get("next") or "").strip().lower()
    notification_state = str(values.get("notification_state") or values.get("notify") or "").strip().lower()
    final_apply_state = str(values.get("final_apply_state") or values.get("review") or "").strip().lower()
    task_type = str(values.get("task_type") or values.get("type") or "").strip().lower()
    final_apply_pending = final_apply_state == "pending" or _line_boolish(values.get("final_apply_pending")) is True
    adopted = _line_boolish(values.get("adopted")) is True

    blocked = (
        explicit_state in {"blocked", "block", "rejected", "reject"}
        or final_apply_state in {"blocked", "rejected"}
        or next_action in _BLOCKED_NEXT_ACTIONS
    )
    if blocked:
        return "blocked"

    pending = (
        explicit_state in {"pending_review", "review_pending"}
        or final_apply_pending
        or next_action in _PENDING_REVIEW_NEXT_ACTIONS
        or completion_state in _PENDING_REVIEW_COMPLETION_STATES
        or (completion_state == "ready_to_adopt" and task_type == "teammate")
    )
    if pending:
        return "pending_review"

    adopted_signal = (
        explicit_state == "adopted"
        or adopted
        or completion_state == "adopted"
        or next_action in _ADOPTED_NEXT_ACTIONS
        or notification_state == "foreground_adopted"
        or final_apply_state == "applied"
    )
    if adopted_signal:
        return "adopted"

    if explicit_state == "returned":
        return "returned"
    if completion_state == "ready_to_adopt":
        return "returned"
    if terminal_state == "completed" or status == "completed":
        return "returned"
    return "pending"


def _line_boolish(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if text in _BOOL_TRUE:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _orchestration_state_counts(lines: list[str]) -> tuple[int, int, int, int]:
    return _state_helpers.orchestration_state_counts(lines)


def _workflow_policy_surface_counts(lines: list[str]) -> tuple[int, int, int]:
    return _state_helpers.workflow_policy_surface_counts(lines)
