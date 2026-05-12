from __future__ import annotations

from typing import Any


def delegated_workflow_text(payload: dict[str, Any]) -> str:
    lines = ["delegated workflow"]
    lines.append(f"agent_id={payload.get('agent_id') or '-'}")
    lines.append(f"role={payload.get('role') or '-'}")
    lines.append(f"status={payload.get('status') or '-'}")
    lines.append(f"workflow_state={payload.get('workflow_state') or '-'}")
    if payload.get("wall_time_ms") not in (None, ""):
        lines.append(f"wall_time_ms={payload['wall_time_ms']}")
    if payload.get("current_step_wall_time_ms") not in (None, ""):
        lines.append(f"current_step_wall_time_ms={payload['current_step_wall_time_ms']}")
    if payload.get("timeout_budget_seconds") not in (None, ""):
        lines.append(f"timeout_budget_seconds={payload['timeout_budget_seconds']}")
    if "timeout_hit" in payload:
        lines.append(f"timeout_hit={'true' if payload.get('timeout_hit') else 'false'}")
    if str(payload.get("timeout_reason") or "").strip():
        lines.append(f"timeout_reason={payload['timeout_reason']}")
    if str(payload.get("timeout_source") or "").strip():
        lines.append(f"timeout_source={payload['timeout_source']}")
    if str(payload.get("terminal_state") or "").strip():
        lines.append(f"terminal_state={payload.get('terminal_state') or '-'}")
    if str(payload.get("terminal_reason") or "").strip():
        lines.append(f"terminal_reason={payload.get('terminal_reason') or '-'}")
    if str(payload.get("resume_source") or "").strip():
        lines.append(f"resume_source={payload.get('resume_source') or '-'}")
    if str(payload.get("completion_policy") or "").strip():
        lines.append(f"completion_policy={payload.get('completion_policy') or '-'}")
    if str(payload.get("completion_state") or "").strip():
        lines.append(f"completion_state={payload.get('completion_state') or '-'}")
    if str(payload.get("result_state") or "").strip():
        lines.append(f"result_state={payload.get('result_state') or '-'}")
    for key in (
        "delegated_result_returned",
        "delegated_result_adopted",
        "delegated_result_pending_review",
        "background_result_returned",
        "background_result_adopted",
        "background_result_pending_review",
    ):
        if payload.get(key) not in (None, ""):
            lines.append(f"{key}={payload.get(key)}")
    if str(payload.get("background_priority") or "").strip():
        lines.append(f"background_priority={payload.get('background_priority') or '-'}")
    if str(payload.get("adoption_expectation") or "").strip():
        lines.append(f"adoption_expectation={payload.get('adoption_expectation') or '-'}")
    if str(payload.get("last_wait_decision") or "").strip():
        lines.append(f"last_wait_decision={payload.get('last_wait_decision') or '-'}")
    if payload.get("last_wait_blocked_ms") not in (None, ""):
        lines.append(f"last_wait_blocked_ms={payload.get('last_wait_blocked_ms')}")
    if "last_wait_timed_out" in payload:
        lines.append(f"last_wait_timed_out={'true' if payload.get('last_wait_timed_out') else 'false'}")
    if str(payload.get("last_wait_reason") or "").strip():
        lines.append(f"last_wait_reason={payload.get('last_wait_reason') or '-'}")
    if str(payload.get("last_wait_at") or "").strip():
        lines.append(f"last_wait_at={payload.get('last_wait_at') or '-'}")
    current_step_id = str(payload.get("current_step_id") or payload.get("live_current_step_id") or "").strip()
    current_step_status = str(payload.get("current_step_status") or payload.get("live_current_step_status") or "").strip()
    current_step_title = str(payload.get("current_step_title") or payload.get("live_current_step_title") or "").strip()
    if current_step_id or current_step_status or current_step_title:
        lines.append(
            "current_step="
            + f"{current_step_id or '-'}"
            + f" | {current_step_status or '-'}"
            + f" | {current_step_title or '-'}"
        )
    live_queued_input_count = payload.get("live_queued_input_count")
    if live_queued_input_count not in (None, ""):
        lines.append(f"queued_input_count={live_queued_input_count}")
    elif payload.get("pending_input_count") not in (None, ""):
        lines.append(f"queued_input_count={payload.get('pending_input_count')}")
    if "live_has_active_input" in payload:
        lines.append(f"has_active_input={'true' if payload.get('live_has_active_input') else 'false'}")
    live_tool_event_count = payload.get("live_last_tool_event_count")
    live_item_event_count = payload.get("live_last_item_event_count")
    live_turn_event_count = payload.get("live_last_turn_event_count")
    if (
        live_tool_event_count not in (None, "")
        or live_item_event_count not in (None, "")
        or live_turn_event_count not in (None, "")
    ):
        lines.append(
            "last_event_count="
            + f"tool:{live_tool_event_count if live_tool_event_count not in (None, '') else 0}"
            + f" item:{live_item_event_count if live_item_event_count not in (None, '') else 0}"
            + f" turn:{live_turn_event_count if live_turn_event_count not in (None, '') else 0}"
        )
    if str(payload.get("live_snapshot_exported_at") or "").strip():
        lines.append(f"snapshot_exported_at={payload.get('live_snapshot_exported_at')}")
    child_identity = dict(payload.get("child_identity") or {})
    if child_identity:
        lines.append(
            "child_identity="
            + f"agent_id:{child_identity.get('agent_id') or '-'}"
            + f" run_id:{child_identity.get('run_id') or '-'}"
            + f" parent_run_id:{child_identity.get('parent_run_id') or '-'}"
            + f" thread_id:{child_identity.get('thread_id') or '-'}"
        )
    lines.append(f"steps={payload.get('step_count') or 0}")
    lines.append(f"checkpoints={payload.get('checkpoint_count') or 0}")
    recovery_actions = [dict(item) for item in list(payload.get("recovery_actions") or []) if isinstance(item, dict)]
    lines.append(f"recovery_actions={len(recovery_actions)}")
    for action in recovery_actions:
        action_step_id = str(action.get("step_id") or "").strip()
        action_detail = f"- {action.get('action') or '-'}"
        if action_step_id:
            action_detail += f" | step={action_step_id}"
        if str(action.get("label") or "").strip():
            action_detail += f" | {action['label']}"
        lines.append(action_detail)
    step_items = [dict(item) for item in list(payload.get("steps") or []) if isinstance(item, dict)]
    if step_items:
        lines.append("recent_steps:")
        for item in step_items:
            line = f"- {item.get('step_id') or '-'} | {item.get('status') or '-'} | {item.get('title') or '-'}"
            if str(item.get("source") or "").strip():
                line += f" | source={item['source']}"
            if int(item.get("retry_attempt") or 0) > 0:
                line += f" | retry_attempt={item['retry_attempt']}"
            lines.append(line)
    checkpoint_items = [dict(item) for item in list(payload.get("checkpoints") or []) if isinstance(item, dict)]
    if checkpoint_items:
        lines.append("recent_checkpoints:")
        for item in checkpoint_items:
            line = f"- {item.get('checkpoint_id') or '-'} | {item.get('status') or '-'} | {item.get('kind') or '-'}"
            if str(item.get("summary") or "").strip():
                line += f" | {item['summary']}"
            lines.append(line)
    return "\n".join(lines)


def delegated_agent_summary_text(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip() or "queued"
    agent_id = str(payload.get("agent_id") or "").strip() or "-"
    model = str(payload.get("model") or "").strip() or "-"
    provider_name = str(payload.get("provider_name") or "").strip() or "-"
    terminal_state = str(payload.get("terminal_state") or "").strip()
    if status == "completed":
        text = str(payload.get("text") or "").strip()
        if text:
            return text
    if status == "closed" and terminal_state in {"closed_by_request", "orphaned", "cancelled"}:
        return f"delegated agent {agent_id} terminal_state={terminal_state}"
    if status == "closed":
        text = str(payload.get("text") or "").strip()
        if text:
            return text
    if status == "failed":
        error = str(payload.get("error") or "").strip() or "delegated agent failed"
        return f"delegated agent {agent_id} failed: {error}"
    scheduler_reason = str(payload.get("scheduler_reason") or "").strip()
    if status == "queued" and scheduler_reason:
        return f"delegated agent {agent_id} queued: {scheduler_reason}"
    return f"delegated agent {agent_id} status={status} provider={provider_name} model={model}"
