from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.ui import status_controller_operator_runtime as operator_runtime


def review_projection_state(
    *,
    result_state: Any,
    completion_state: Any,
    final_apply_state: Any,
) -> str:
    normalized_result = operator_runtime.normalized_status(result_state)
    normalized_completion = operator_runtime.normalized_status(completion_state)
    normalized_review = operator_runtime.normalized_status(final_apply_state)
    if normalized_review == "blocked" or normalized_result in {"blocked", "block", "rejected", "reject"}:
        return "blocked"
    if normalized_review in {"pending", "review_pending"}:
        return "pending"
    if normalized_result in {"pending_review", "review_pending"}:
        return "pending"
    if normalized_result:
        return ""
    if normalized_completion in {"ready_to_adopt", "awaiting_join", "pending_review"}:
        return "pending"
    return ""


def single_operator_result_hint(
    command_name: str,
    *,
    key_values: dict[str, str],
    tool_label_fn: Callable[[str], str],
    boolish_status_fn: Callable[[Any], bool | None],
    tenant_scope_parts_fn: Callable[..., list[str]],
    review_projection_state_fn: Callable[..., str],
) -> str:
    task_id = str(key_values.get("task_id") or "").strip()
    agent_id = str(key_values.get("agent_id") or "").strip()
    role = str(key_values.get("role") or "").strip()
    tenant_id = str(key_values.get("tenant_id") or "").strip()
    workspace_scope = str(key_values.get("workspace_scope") or "").strip()
    tenant_scope_profile = str(key_values.get("tenant_scope_profile") or "").strip()
    status = str(key_values.get("status") or "").strip()
    workflow_state = str(key_values.get("workflow_state") or "").strip()
    queue_state = str(key_values.get("queue_state") or "").strip()
    completion_state = str(key_values.get("completion_state") or "").strip()
    result_state = str(key_values.get("result_state") or "").strip()
    adoption_expectation = str(key_values.get("adoption_expectation") or "").strip()
    terminal_state = str(key_values.get("terminal_state") or "").strip()
    final_apply_state = str(key_values.get("final_apply_state") or "").strip()
    scheduler_reason = str(key_values.get("scheduler_reason") or "").strip()
    terminal_reason = str(key_values.get("terminal_reason") or "").strip()
    summary = str(key_values.get("summary") or "").strip()
    policy_surface = str(key_values.get("command_policy_surface") or "").strip()
    adopted = boolish_status_fn(key_values.get("adopted"))
    timed_out = boolish_status_fn(key_values.get("timed_out"))
    timeout_hit = boolish_status_fn(key_values.get("timeout_hit"))

    if command_name.startswith("background_task"):
        subject = f"task {task_id}" if task_id not in {"", "-"} else ""
    else:
        if agent_id not in {"", "-"}:
            subject = f"agent {agent_id}"
        elif role not in {"", "-"}:
            subject = tool_label_fn(role)
        else:
            subject = ""
    if not subject:
        return ""

    parts = [subject]
    parts.extend(
        tenant_scope_parts_fn(
            tenant_id,
            workspace_scope,
            tenant_scope_profile,
            tool_label_fn=tool_label_fn,
        )
    )
    primary_state = operator_runtime.operator_primary_state(
        status=status,
        workflow_state=workflow_state,
        queue_state=queue_state,
        completion_state=completion_state,
        result_state=result_state,
        adoption_expectation=adoption_expectation,
        terminal_state=terminal_state,
        adopted=adopted,
        timed_out=timed_out,
        timeout_hit=timeout_hit,
    )
    if primary_state not in {"", "-"}:
        parts.append(tool_label_fn(primary_state))
    review_state = review_projection_state_fn(
        result_state=result_state,
        completion_state=completion_state,
        final_apply_state=final_apply_state,
    )
    if review_state:
        parts.append(f"review {tool_label_fn(review_state)}")
    elif final_apply_state not in {"", "-"}:
        parts.append(f"review {tool_label_fn(final_apply_state)}")
    if adoption_expectation not in {"", "-"} and operator_runtime.normalized_status(primary_state) in {
        "",
        "returned",
        "completed",
    }:
        parts.append(f"next {tool_label_fn(adoption_expectation)}")
    if not policy_surface:
        policy_surface = operator_runtime.policy_surface_hint(
            key_values.get("command_policies") or key_values.get("command_policy")
        )
    detail = scheduler_reason or terminal_reason or summary
    if policy_surface:
        detail = f"{detail} · {policy_surface}" if detail else policy_surface
    if detail not in {"", "-"}:
        parts.append(tool_label_fn(detail))
    return " · ".join(parts)


def format_elapsed_compact(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def pending_approval_count(status_data: dict[str, Any]) -> int:
    try:
        return max(0, int(str(status_data.get("pending_approvals", "0") or "0").strip()))
    except ValueError:
        return 0


def build_operator_surface_hint(
    status_data: dict[str, Any],
    *,
    width: int,
    short_fn: Callable[[str, int], str],
    crop_one_line_fn: Callable[[str, int], str],
    tool_label_fn: Callable[[str], str],
    boolish_status_fn: Callable[[Any], bool | None],
    tenant_scope_parts_fn: Callable[..., list[str]],
    review_projection_state_fn: Callable[..., str],
) -> str:
    operator_hint_text = str(status_data.get("operator_hint_text") or "").strip()
    status = str(status_data.get("status") or "").strip()
    workflow_state = str(status_data.get("workflow_state") or "").strip()
    queue_state = str(status_data.get("queue_state") or "").strip()
    completion_state = str(status_data.get("completion_state") or "").strip()
    result_state = str(status_data.get("result_state") or "").strip()
    adoption_expectation = str(status_data.get("adoption_expectation") or "").strip()
    terminal_state = str(status_data.get("terminal_state") or "").strip()
    scheduler_reason = str(status_data.get("scheduler_reason") or "").strip()
    terminal_reason = str(status_data.get("terminal_reason") or "").strip()
    final_apply_state = str(status_data.get("final_apply_state") or "").strip()
    summary = str(status_data.get("summary") or "").strip()
    command_policies = status_data.get("command_policies")
    adopted = boolish_status_fn(status_data.get("adopted"))
    timed_out = boolish_status_fn(status_data.get("timed_out"))
    timeout_hit = boolish_status_fn(status_data.get("timeout_hit"))
    task_id = str(status_data.get("task_id") or "").strip()
    agent_id = str(status_data.get("agent_id") or "").strip()
    role = str(status_data.get("role") or "").strip()
    tenant_id = str(status_data.get("tenant_id") or "").strip()
    workspace_scope = str(status_data.get("workspace_scope") or "").strip()
    tenant_scope_profile = str(status_data.get("tenant_scope_profile") or "").strip()

    if not any(
        value not in {"", "-"}
        for value in (
            task_id,
            agent_id,
            role,
            tenant_id,
            workspace_scope,
            status,
            workflow_state,
            queue_state,
            completion_state,
            result_state,
            adoption_expectation,
            terminal_state,
            final_apply_state,
        )
    ):
        if operator_hint_text not in {"", "-"}:
            return crop_one_line_fn(f"• {operator_hint_text}", width)
        return ""

    if task_id not in {"", "-"}:
        subject = f"task {short_fn(task_id, 16)}"
    elif agent_id not in {"", "-"}:
        subject = f"agent {short_fn(agent_id, 16)}"
    elif role not in {"", "-"}:
        subject = tool_label_fn(role)
    else:
        subject = "workflow"

    parts = [subject]
    parts.extend(
        tenant_scope_parts_fn(
            tenant_id,
            workspace_scope,
            tenant_scope_profile,
            tool_label_fn=tool_label_fn,
        )
    )
    primary_state = operator_runtime.operator_primary_state(
        status=status,
        workflow_state=workflow_state,
        queue_state=queue_state,
        completion_state=completion_state,
        result_state=result_state,
        adoption_expectation=adoption_expectation,
        terminal_state=terminal_state,
        adopted=adopted,
        timed_out=timed_out,
        timeout_hit=timeout_hit,
    )
    if primary_state not in {"", "-"}:
        parts.append(tool_label_fn(primary_state))
    if workflow_state not in {"", "-", primary_state, queue_state}:
        parts.append(f"workflow {tool_label_fn(workflow_state)}")
    if queue_state not in {"", "-", primary_state, workflow_state}:
        parts.append(f"queue {tool_label_fn(queue_state)}")
    if completion_state not in {"", "-", primary_state, workflow_state, queue_state}:
        parts.append(f"completion {tool_label_fn(completion_state)}")
    if adopted is True and operator_runtime.normalized_status(primary_state) != "adopted":
        parts.append("adopted")
    if adoption_expectation not in {"", "-"}:
        parts.append(f"next {tool_label_fn(adoption_expectation)}")
    review_state = review_projection_state_fn(
        result_state=result_state,
        completion_state=completion_state,
        final_apply_state=final_apply_state,
    )
    if review_state:
        parts.append(f"review {tool_label_fn(review_state)}")
    elif final_apply_state not in {"", "-"}:
        parts.append(f"review {tool_label_fn(final_apply_state)}")
    if (timed_out is True or timeout_hit is True) and operator_runtime.normalized_status(primary_state) != "timed_out":
        parts.append("timed out")
    detail = scheduler_reason or terminal_reason or summary
    policy_hint = operator_runtime.policy_surface_hint(command_policies)
    if policy_hint:
        detail = f"{detail} · {policy_hint}" if detail else policy_hint
    text = "• " + " · ".join(parts)
    if detail:
        text += f" · {detail}"
    return crop_one_line_fn(text, width)


def busy_label_for_queued_request(
    text: str,
    *,
    queued_request_busy_label_keys: dict[str, str],
    translate_fn: Callable[[str], str],
) -> str:
    request_text = str(text or "").strip()
    if not request_text.startswith("/"):
        return translate_fn("status.working")
    command_name = operator_runtime.operator_command_name(request_text)
    if not command_name:
        return translate_fn("status.working")
    key = queued_request_busy_label_keys.get(command_name)
    return translate_fn(key) if key else translate_fn("status.working")
