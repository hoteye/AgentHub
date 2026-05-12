from __future__ import annotations

from typing import Any, Callable

from . import tasks_teammate_runtime_helpers
from .models import BackgroundTaskStatus


def teammate_response_projection(
    *,
    response_payload: dict[str, Any] | None,
    live_cwd: Any,
    response_status_mapping_fn: Callable[[Any], dict[str, Any]],
    mapping_dict_fn: Callable[[Any], dict[str, Any]],
    route_report_from_status_fn: Callable[[dict[str, Any]], dict[str, Any]],
    teammate_commands_fn: Callable[[dict[str, Any]], list[str]],
    teammate_test_commands_fn: Callable[[list[str]], list[str]],
    teammate_modified_files_fn: Callable[[dict[str, Any], Any], list[str]],
) -> dict[str, Any]:
    assistant_text = ""
    tool_event_names: list[str] = []
    commands: list[str] = []
    test_commands: list[str] = []
    response_status: dict[str, Any] = {}
    protocol_diagnostics: dict[str, Any] = {}
    route_report: dict[str, Any] = {}
    modified_files: list[str] = []
    command_policies: list[dict[str, Any]] = []
    if isinstance(response_payload, dict):
        assistant_text = str(response_payload.get("assistant_text") or "").strip()
        response_status = response_status_mapping_fn(response_payload.get("status"))
        protocol_diagnostics = mapping_dict_fn(response_payload.get("protocol_diagnostics"))
        route_report = route_report_from_status_fn(response_status)
        tool_event_names = [
            str(item.get("name") or "").strip()
            for item in list(response_payload.get("tool_events") or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        commands = teammate_commands_fn(response_payload)
        test_commands = teammate_test_commands_fn(commands)
        modified_files = teammate_modified_files_fn(response_payload, cwd=live_cwd)
        command_policies = _command_policy_projection(response_payload)
    return {
        "assistant_text": assistant_text,
        "tool_event_names": tool_event_names,
        "commands": commands,
        "test_commands": test_commands,
        "response_status": response_status,
        "protocol_diagnostics": protocol_diagnostics,
        "route_report": route_report,
        "modified_files": modified_files,
        "command_policies": command_policies,
    }


def staged_review_projection(
    *,
    envelope_task_id: str,
    task_text: str,
    live_cwd: Any,
    stage_cwd: Any,
    bootstrap_diagnostics: dict[str, Any],
    route_report: dict[str, Any],
    allowed_paths: list[str],
    blocked_paths: list[str],
    commands: list[str],
    test_commands: list[str],
    workspace_changes: list[dict[str, Any]],
    paths_outside_policy_fn: Callable[..., list[str]],
    teammate_review_commands_fn: Callable[[str, bool], list[str]],
) -> dict[str, Any]:
    modified_files = [
        str(item.get("path") or "").strip()
        for item in workspace_changes
        if str(item.get("path") or "").strip()
    ]
    out_of_scope_files = paths_outside_policy_fn(
        modified_files,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
    )
    final_apply_pending = bool(modified_files) and not out_of_scope_files
    final_apply_state = (
        "blocked"
        if out_of_scope_files
        else "pending"
        if final_apply_pending
        else "not_required"
    )
    review_commands = teammate_review_commands_fn(envelope_task_id, blocked=bool(out_of_scope_files)) if modified_files else []
    return {
        "modified_files": modified_files,
        "out_of_scope_files": out_of_scope_files,
        "final_apply_pending": final_apply_pending,
        "final_apply_state": final_apply_state,
        "review_commands": review_commands,
        "review_payload": {
            "task_id": envelope_task_id,
            "task_text": task_text,
            "live_cwd": str(live_cwd),
            "stage_cwd": str(stage_cwd),
            "bootstrap_diagnostics": bootstrap_diagnostics,
            "route_report": route_report,
            "allowed_paths": allowed_paths,
            "blocked_paths": blocked_paths,
            "modified_files": modified_files,
            "out_of_scope_files": out_of_scope_files,
            "final_apply_pending": final_apply_pending,
            "final_apply_state": final_apply_state,
            "commands": commands,
            "test_commands": test_commands,
            "changes": workspace_changes,
            "review_commands": review_commands,
        },
    }


def teammate_task_outcome(
    *,
    task_id: str,
    run: Any,
    assistant_text: str,
    staged_workspace: bool,
    out_of_scope_files: list[str],
    final_apply_pending: bool,
    final_apply_state: str,
    modified_files: list[str],
    trim_error_fn: Callable[[str], str],
    timeout_error_text_fn: Callable[[str, float | None], str],
) -> dict[str, Any]:
    if run.cancelled:
        status = BackgroundTaskStatus.CANCELLED
        summary = "teammate task cancelled"
        error_text = ""
    elif run.timed_out:
        status = BackgroundTaskStatus.FAILED
        summary = "teammate task timed out"
        error_text = timeout_error_text_fn("teammate", run.timeout_seconds)
    elif run.returncode == 0:
        if staged_workspace and out_of_scope_files:
            status = BackgroundTaskStatus.FAILED
            summary = "teammate staged changes blocked by path policy"
            error_text = trim_error_fn("out-of-scope staged changes: " + ", ".join(out_of_scope_files[:8]), max_chars=320)
        elif staged_workspace and final_apply_pending:
            status = BackgroundTaskStatus.COMPLETED
            summary = assistant_text or "teammate staged changes ready for final apply"
            error_text = ""
        elif staged_workspace:
            status = BackgroundTaskStatus.COMPLETED
            summary = assistant_text or "teammate staged run completed with no changes"
            error_text = ""
        else:
            status = BackgroundTaskStatus.COMPLETED
            summary = assistant_text or "teammate task completed"
            error_text = ""
    else:
        status = BackgroundTaskStatus.FAILED
        summary = assistant_text or "teammate task failed"
        error_text = trim_error_fn(run.stderr or run.stdout or f"teammate exited {run.returncode}")
    review_commands = []
    next_final_apply_pending = final_apply_pending
    next_final_apply_state = final_apply_state
    if staged_workspace and status != BackgroundTaskStatus.COMPLETED and final_apply_state == "pending":
        next_final_apply_pending = False
        next_final_apply_state = "failed"
        review_commands = [f"/background_task_reject {task_id}"] if modified_files else []
    return {
        "status": status,
        "summary": summary,
        "error_text": error_text,
        "final_apply_pending": next_final_apply_pending,
        "final_apply_state": next_final_apply_state,
        "review_commands": review_commands,
    }


def new_headless_jsonl_state() -> dict[str, Any]:
    return {
        "thread_id": "",
        "assistant_text": "",
        "commentary_text": "",
        "latest_reasoning_text": "",
        "turn_events": [],
        "tool_events": [],
        "event_count": 0,
    }


def consume_headless_jsonl_line(state: dict[str, Any], line: str) -> dict[str, Any]:
    return tasks_teammate_runtime_helpers.consume_headless_jsonl_line_impl(
        state,
        line,
        reasoning_text_fn=_reasoning_text,
        command_execution_payload_fn=_command_execution_payload,
        structured_payload_from_tool_item_fn=_structured_payload_from_tool_item,
    )


def synthetic_response_payload_from_jsonl_state(state: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "assistant_text": str(state.get("assistant_text") or ""),
        "commentary_text": str(state.get("commentary_text") or ""),
        "tool_events": list(state.get("tool_events") or []),
        "turn_events": list(state.get("turn_events") or []),
    }
    thread_id = str(state.get("thread_id") or "").strip()
    if thread_id:
        payload["thread_id"] = thread_id
    return payload


def running_summary_text(state: dict[str, Any]) -> str:
    for candidate in (
        str(state.get("commentary_text") or "").strip(),
        str(state.get("assistant_text") or "").strip(),
        str(state.get("latest_reasoning_text") or "").strip(),
    ):
        if candidate:
            return candidate
    return "running"


def _reasoning_text(item: dict[str, Any]) -> str:
    text = str(item.get("text") or "").strip()
    if text:
        return text
    summary = item.get("summary")
    if not isinstance(summary, list):
        return ""
    parts: list[str] = []
    for entry in summary:
        if isinstance(entry, dict):
            entry_text = str(entry.get("text") or "").strip()
        else:
            entry_text = str(entry or "").strip()
        if entry_text:
            parts.append(entry_text)
    return "\n\n".join(parts)


def _structured_payload_from_tool_item(item: dict[str, Any]) -> dict[str, Any]:
    result = item.get("result")
    structured = result.get("structured_content") if isinstance(result, dict) else None
    if isinstance(structured, dict):
        return dict(structured)
    payload: dict[str, Any] = {}
    arguments = item.get("arguments")
    if isinstance(arguments, dict):
        payload.update(dict(arguments))
    elif arguments not in (None, ""):
        payload["arguments"] = arguments
    if structured not in (None, ""):
        payload["structured_content"] = structured
    error = item.get("error")
    if isinstance(error, dict) and str(error.get("message") or "").strip():
        payload["error"] = str(error.get("message") or "").strip()
    return payload


def _command_execution_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "command": str(item.get("command") or "").strip(),
        "aggregated_output": str(item.get("aggregated_output") or ""),
        "exit_code": item.get("exit_code"),
        "status": str(item.get("status") or "").strip(),
    }
    effective_command = str(item.get("effective_command") or "").strip()
    if effective_command:
        payload["effective_command"] = effective_command
    raw_error_code = str(item.get("error_code") or "").strip()
    if raw_error_code:
        payload["error_code"] = raw_error_code
    command_policy = item.get("command_policy")
    if isinstance(command_policy, dict):
        payload["command_policy"] = dict(command_policy)
    if str(payload.get("status") or "").strip().lower() == "policy_denied" and "command_policy" not in payload:
        denied_policy: dict[str, Any] = {"allowed": False}
        if raw_error_code:
            denied_policy["error_code"] = raw_error_code
        payload["command_policy"] = denied_policy
    return payload


def _command_policy_projection(response_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return tasks_teammate_runtime_helpers.command_policy_projection_impl(response_payload)
