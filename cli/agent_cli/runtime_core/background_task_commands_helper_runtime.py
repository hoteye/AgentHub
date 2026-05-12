from __future__ import annotations

import shlex
from typing import Any, Callable


def wait_summary_fragment(payload: dict[str, Any]) -> str:
    decision = str(payload.get("last_wait_decision") or "").strip()
    if not decision:
        return ""
    blocked_ms = payload.get("last_wait_blocked_ms")
    detail = decision
    if blocked_ms not in (None, ""):
        detail += f":{blocked_ms}ms"
    if payload.get("last_wait_timed_out"):
        detail += ":timed_out"
    return detail


def parse_background_benchmark_args(
    raw_args: str,
    *,
    parse_positive_float_fn: Callable[..., float],
) -> tuple[list[str], dict[str, Any]]:
    try:
        tokens = shlex.split(str(raw_args or "").strip(), posix=True)
    except ValueError as exc:
        raise ValueError(f"failed to parse background benchmark args: {exc}") from exc
    timeout_seconds = ""
    argv: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--timeout-seconds":
            if index + 1 >= len(tokens):
                raise ValueError("failed to parse background benchmark args: missing value for --timeout-seconds")
            timeout_seconds = str(tokens[index + 1] or "").strip()
            index += 2
            continue
        argv.append(token)
        index += 1
    timeout_payload: dict[str, Any] = {}
    if timeout_seconds:
        timeout_payload["timeout_seconds"] = parse_positive_float_fn(
            timeout_seconds,
            option_name="--timeout-seconds",
        )
    return argv, timeout_payload


def parse_background_smoke_args(
    raw_args: str,
    *,
    parse_positive_float_fn: Callable[..., float],
) -> tuple[str, list[str], dict[str, Any]]:
    try:
        tokens = shlex.split(str(raw_args or "").strip(), posix=True)
    except ValueError as exc:
        raise ValueError(f"failed to parse background smoke args: {exc}") from exc
    kind = "multi_llm"
    forwarded: list[str] = []
    timeout_seconds = ""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--kind":
            if index + 1 >= len(tokens):
                raise ValueError("failed to parse background smoke args: missing value for --kind")
            kind = str(tokens[index + 1] or "").strip() or kind
            index += 2
            continue
        if token == "--timeout-seconds":
            if index + 1 >= len(tokens):
                raise ValueError("failed to parse background smoke args: missing value for --timeout-seconds")
            timeout_seconds = str(tokens[index + 1] or "").strip()
            index += 2
            continue
        if index == 0 and not token.startswith("--"):
            kind = str(token or "").strip() or kind
            index += 1
            continue
        forwarded.append(token)
        index += 1
    timeout_payload: dict[str, Any] = {}
    if timeout_seconds:
        timeout_payload["timeout_seconds"] = parse_positive_float_fn(
            timeout_seconds,
            option_name="--timeout-seconds",
        )
    return kind, forwarded, timeout_payload


def background_task_overview_line(
    item: Any,
    *,
    status_payload: dict[str, Any] | None,
    preview_text_fn: Callable[..., str],
) -> str:
    artifact = dict(getattr(item, "artifact", {}) or {})
    artifact_path = str(artifact.get("report_path") or artifact.get("snapshot_path") or "").strip()
    task_type = str(artifact.get("task_type") or "").strip()
    dispatch_id = artifact.get("dispatch_id")
    cancel_requested = bool(artifact.get("cancel_requested"))
    queue_state = str(artifact.get("queue_state") or "").strip()
    if isinstance(status_payload, dict):
        task_type = str(status_payload.get("task_type") or task_type).strip()
        dispatch_id = status_payload.get("dispatch_id") or dispatch_id
        cancel_requested = bool(status_payload.get("cancel_requested")) or cancel_requested
        queue_state = str(status_payload.get("queue_state") or queue_state).strip()
    step_count = artifact.get("step_count")
    checkpoint_count = artifact.get("checkpoint_count")
    workflow_state = str(artifact.get("workflow_state") or "").strip()
    recovery_action_count = artifact.get("recovery_action_count")
    notification_state = str(artifact.get("notification_state") or "").strip()
    terminal_state = str(artifact.get("terminal_state") or "").strip()
    terminal_reason = str(artifact.get("terminal_reason") or "").strip()
    wall_time_ms = artifact.get("wall_time_ms")
    timeout_reason = str(artifact.get("timeout_reason") or "").strip()
    wait_summary = wait_summary_fragment(artifact)
    current_step_id = str(artifact.get("current_step_id") or "").strip()
    current_step_status = str(artifact.get("current_step_status") or "").strip()
    current_step_title = str(artifact.get("current_step_title") or "").strip()
    summary = str(getattr(item, "summary", "-") or "-").strip() or "-"
    status_value = str(getattr(getattr(item, "status", None), "value", getattr(item, "status", "")) or "").strip()
    line = f"- {item.task_id} | {status_value} | {summary}"
    if task_type:
        line += f" | type={task_type}"
    if dispatch_id not in (None, "", 0):
        line += f" | dispatch={dispatch_id}"
    if queue_state and queue_state != status_value:
        line += f" | queue={queue_state}"
    if cancel_requested:
        line += " | cancel=requested"
    if artifact_path:
        line += f" | artifact={artifact_path}"
    if workflow_state:
        line += f" | workflow={workflow_state}"
    if step_count not in (None, ""):
        line += f" | steps={step_count}"
    if checkpoint_count not in (None, ""):
        line += f" | checkpoints={checkpoint_count}"
    if recovery_action_count not in (None, ""):
        line += f" | recoveries={recovery_action_count}"
    if notification_state:
        line += f" | notify={notification_state}"
    if terminal_state:
        line += f" | terminal_state={terminal_state}"
    if terminal_reason:
        line += f" | terminal={terminal_reason}"
    if wall_time_ms not in (None, ""):
        line += f" | wall={wall_time_ms}ms"
    if timeout_reason:
        line += f" | timeout_reason={timeout_reason}"
    if wait_summary:
        line += f" | wait={wait_summary}"
    if bool(artifact.get("timed_out")):
        line += " | timeout=true"
    elif "timeout_hit" in artifact:
        line += f" | timeout={'true' if artifact.get('timeout_hit') else 'false'}"
    final_apply_state = str(artifact.get("final_apply_state") or "").strip()
    if bool(artifact.get("final_apply_pending")) and not final_apply_state:
        final_apply_state = "pending"
    if final_apply_state:
        line += f" | review={final_apply_state}"
    if current_step_title:
        line += f" | current={current_step_status or current_step_id or '-'}:{preview_text_fn(current_step_title, max_chars=32)}"
    elif current_step_id or current_step_status:
        line += f" | current={current_step_id or '-'}:{current_step_status or '-'}"
    return line


def delegated_workflow_line(
    payload: dict[str, Any],
    *,
    preview_text_fn: Callable[..., str],
) -> tuple[str, str | None]:
    agent_id = str(payload.get("agent_id") or "").strip()
    role = str(payload.get("role") or "").strip() or "-"
    status = str(payload.get("status") or "").strip() or "-"
    line = f"- delegated | {agent_id} | {status} | role={role}"
    workflow_state = str(payload.get("workflow_state") or "").strip()
    if workflow_state:
        line += f" | workflow={workflow_state}"
    terminal_state = str(payload.get("terminal_state") or "").strip()
    wall_time_ms = payload.get("wall_time_ms")
    timeout_reason = str(payload.get("timeout_reason") or "").strip()
    wait_summary = wait_summary_fragment(payload)
    if terminal_state:
        line += f" | terminal_state={terminal_state}"
    if wall_time_ms not in (None, ""):
        line += f" | wall={wall_time_ms}ms"
    if timeout_reason:
        line += f" | timeout_reason={timeout_reason}"
    if wait_summary:
        line += f" | wait={wait_summary}"
    completion_state = str(payload.get("completion_state") or "").strip()
    if completion_state:
        line += f" | completion={completion_state}"
    provider_name = str(payload.get("provider_name") or "").strip()
    model = str(payload.get("model") or "").strip()
    if provider_name or model:
        line += f" | model={provider_name or '-'}:{model or '-'}"
    current_step_status = str(payload.get("current_step_status") or "").strip()
    current_step_title = str(payload.get("current_step_title") or "").strip()
    current_step_id = str(payload.get("current_step_id") or "").strip()
    if current_step_title:
        line += f" | current={current_step_status or current_step_id or '-'}:{preview_text_fn(current_step_title, max_chars=32)}"
    elif current_step_status or current_step_id:
        line += f" | current={current_step_id or '-'}:{current_step_status or '-'}"
    result_contract = payload.get("result_contract")
    if isinstance(result_contract, dict):
        next_action = str(result_contract.get("next_action") or "").strip()
        if next_action:
            line += f" | next={next_action}"
    goal = workflow_goal_text(payload)
    if goal:
        line += f" | goal={preview_text_fn(goal, max_chars=48)}"
    mirrored_task_id = None
    if role.lower() == "teammate" and str(payload.get("delegation_mode") or "").strip().lower() == "background":
        mirrored_task_id = f"bg_delegate_{agent_id}"
    return line, mirrored_task_id


def background_workflow_line(
    item: Any,
    *,
    preview_text_fn: Callable[..., str],
) -> str:
    artifact = dict(getattr(item, "artifact", {}) or {})
    artifact_path = str(artifact.get("report_path") or artifact.get("snapshot_path") or "").strip()
    workflow_state = str(artifact.get("workflow_state") or "").strip()
    terminal_state = str(artifact.get("terminal_state") or "").strip()
    terminal_reason = str(artifact.get("terminal_reason") or "").strip()
    wall_time_ms = artifact.get("wall_time_ms")
    timeout_reason = str(artifact.get("timeout_reason") or "").strip()
    wait_summary = wait_summary_fragment(artifact)
    current_step_id = str(artifact.get("current_step_id") or "").strip()
    current_step_status = str(artifact.get("current_step_status") or "").strip()
    current_step_title = str(artifact.get("current_step_title") or "").strip()
    summary = str(getattr(item, "summary", "-") or "-").strip() or "-"
    status_value = str(getattr(getattr(item, "status", None), "value", getattr(item, "status", "")) or "").strip() or "-"
    task_id = str(getattr(item, "task_id", "") or "").strip() or "-"
    line = f"- background | {task_id} | {status_value} | {summary}"
    if workflow_state:
        line += f" | workflow={workflow_state}"
    if str(artifact.get("notification_state") or "").strip():
        line += f" | notify={artifact['notification_state']}"
    if terminal_state:
        line += f" | terminal_state={terminal_state}"
    if terminal_reason:
        line += f" | terminal={terminal_reason}"
    if wall_time_ms not in (None, ""):
        line += f" | wall={wall_time_ms}ms"
    if timeout_reason:
        line += f" | timeout_reason={timeout_reason}"
    if wait_summary:
        line += f" | wait={wait_summary}"
    if artifact_path:
        line += f" | artifact={artifact_path}"
    if current_step_title:
        line += f" | current={current_step_status or current_step_id or '-'}:{preview_text_fn(current_step_title, max_chars=32)}"
    elif current_step_id or current_step_status:
        line += f" | current={current_step_id or '-'}:{current_step_status or '-'}"
    return line


def workflow_goal_text(payload: dict[str, Any]) -> str:
    result_contract = payload.get("result_contract")
    if isinstance(result_contract, dict) and str(result_contract.get("goal") or "").strip():
        return str(result_contract.get("goal") or "").strip()
    active_input = payload.get("active_input")
    if isinstance(active_input, dict) and str(active_input.get("message") or "").strip():
        return str(active_input.get("message") or "").strip()
    if str(payload.get("active_input_text") or "").strip():
        return str(payload.get("active_input_text") or "").strip()
    if str(payload.get("last_input_text") or "").strip():
        return str(payload.get("last_input_text") or "").strip()
    return ""
