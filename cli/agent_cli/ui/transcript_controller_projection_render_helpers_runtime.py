from __future__ import annotations

import json
from typing import Any, Callable

from .transcript_controller_projection_render_operator_helpers_runtime import (
    operator_background_task_detail_lines as _operator_background_task_detail_lines,
    operator_workflow_detail_lines as _operator_workflow_detail_lines,
    single_operator_detail_line as _single_operator_detail_line,
)


def workflow_next_op(
    *,
    workflow_type: str,
    run_id: str,
    card_id: str,
    task_id: str,
    action_name: str,
    workflow_state: str,
    phase: str,
    status: str,
) -> str:
    action = str(action_name or "").strip().lower()
    workflow = str(workflow_state or "").strip().lower()
    phase_text = str(phase or "").strip().lower()
    status_text = str(status or "").strip().lower()
    orchestration_terminal = {
        "completed",
        "failed",
        "timed_out",
        "cancelled",
        "closed_by_request",
        "orphaned",
        "closed",
        "terminal",
    }
    background_retriable = {"failed", "timed_out", "timeout", "orphaned"}
    delegated_recoverable = {"failed", "timed_out", "timeout", "orphaned"}
    if workflow_type == "orchestration":
        if action in {"apply", "accept"} and run_id and card_id:
            return f"/orchestrate_apply {run_id} {card_id}"
        if action in {"reject", "block", "rework"} and run_id and card_id:
            return f"/orchestrate_reject {run_id} {card_id}"
        if action in {"continue", "resume", "dispatch"} and run_id:
            return f"/orchestrate_continue {run_id}"
        if action in {"progress", "status"} and run_id:
            return f"/orchestrate_progress {run_id}"
        if run_id:
            if status_text in orchestration_terminal or workflow in orchestration_terminal:
                return f"/orchestrate_progress {run_id}"
            if "timeout" in phase_text or "orphan" in phase_text:
                return f"/orchestrate_progress {run_id}"
            if card_id and any(token in phase_text for token in ("review", "pending")):
                return f"/orchestrate_apply {run_id} {card_id}"
            if status_text in {"blocked", "review"} or workflow in {"blocked", "review"}:
                return f"/orchestrate_progress {run_id}"
            return f"/orchestrate_continue {run_id}"
    if workflow_type == "background" and task_id:
        if action in {"wait", "join"}:
            return f"/background_task_status {task_id}"
        if action in {"apply", "accept"}:
            return f"/background_task_apply {task_id}"
        if action in {"reject", "block", "rework"}:
            return f"/background_task_reject {task_id}"
        if action in {"cancel", "abort", "stop"}:
            return f"/background_task_cancel {task_id}"
        if action in {"retry", "rerun"}:
            return f"/background_task_retry {task_id}"
        if status_text in background_retriable or workflow in background_retriable:
            return f"/background_task_retry {task_id}"
        if "timeout" in phase_text or "orphan" in phase_text:
            return f"/background_task_retry {task_id}"
        return f"/background_task_status {task_id}"
    if workflow_type == "delegated" and task_id:
        if action in {"wait", "join"}:
            return f"/wait_agent {task_id}"
        if action in {"resume", "continue"}:
            return f"/resume_agent {task_id}"
        if action in {"close", "stop", "cancel"}:
            return f"/close_agent {task_id}"
        if status_text in delegated_recoverable or workflow in delegated_recoverable:
            return f"/resume_agent {task_id}"
        if "timeout" in phase_text or "orphan" in phase_text:
            return f"/resume_agent {task_id}"
        return f"/agent_workflow {task_id}"
    return ""


def policy_surface(value: Any) -> str:
    entries: list[dict[str, Any]] = []
    if isinstance(value, list):
        entries = [item for item in value if isinstance(item, dict)]
    elif isinstance(value, dict):
        entries = [value]
    else:
        text = str(value or "").strip()
        if text and text != "-":
            try:
                loaded = json.loads(text)
            except (TypeError, ValueError, json.JSONDecodeError):
                loaded = None
            if isinstance(loaded, list):
                entries = [item for item in loaded if isinstance(item, dict)]
            elif isinstance(loaded, dict):
                entries = [loaded]
    if not entries:
        return ""
    denied = [item for item in entries if bool(item.get("policy_denied"))]
    if denied:
        denied_cmd = str(denied[0].get("command") or denied[0].get("effective_command") or "").strip()
        return f"policy denied {denied_cmd}" if denied_cmd else "policy denied"
    for item in entries:
        source = str(item.get("command") or "").strip()
        target = str(item.get("effective_command") or "").strip()
        if source and target and source != target:
            return f"policy rewrite {source} -> {target}"
    return f"policy checked {len(entries)}"


def json_compact(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def mapping_compact(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    parsed = json_compact(value)
    if isinstance(parsed, dict):
        return dict(parsed)
    return {}


def workflow_nested_value(keyed: dict[str, str], key: str) -> Any:
    direct = keyed.get(key)
    if direct not in (None, "", "-"):
        return direct
    for container_key in ("progress_payload", "progress", "projection_payload", "payload"):
        nested = mapping_compact(keyed.get(container_key))
        if key in nested:
            return nested.get(key)
    return None


def count_compact(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    text = str(value or "").strip()
    if text.isdigit():
        return max(0, int(text))
    parsed = json_compact(value)
    if isinstance(parsed, list):
        return len(parsed)
    if isinstance(parsed, dict):
        return len(parsed)
    return 0


def string_items_compact(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip() and str(item).strip() != "-"]
    parsed = json_compact(value)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip() and str(item).strip() != "-"]
    text = str(value or "").strip()
    if not text or text == "-":
        return []
    if "," in text:
        return [segment.strip() for segment in text.split(",") if segment.strip() and segment.strip() != "-"]
    return [text]


def card_ids_compact(value: Any) -> list[str]:
    parsed = json_compact(value)
    if not isinstance(parsed, list):
        return []
    card_ids: list[str] = []
    for item in parsed:
        if isinstance(item, dict):
            card_id = str(item.get("card_id") or "").strip()
            if card_id:
                card_ids.append(card_id)
    return card_ids


def preview_items(items: list[str], *, limit: int = 3) -> str:
    compact = [str(item).strip() for item in list(items or []) if str(item).strip()]
    if not compact:
        return ""
    head = compact[: max(1, int(limit))]
    if len(compact) <= len(head):
        return ",".join(head)
    return f"{','.join(head)} +{len(compact) - len(head)}"


def operator_next_command(value: Any) -> str:
    parsed = json_compact(value)
    if not isinstance(parsed, list):
        return ""
    for item in parsed:
        if not isinstance(item, dict):
            continue
        command_name = str(item.get("command_name") or "").strip()
        if command_name:
            return command_name
        command = str(item.get("command") or "").strip()
        if command:
            return command.split(" ", 1)[0].strip()
    return ""


def followup_summary(value: Any, *, preview_items_fn: Callable[[list[str]], str]) -> tuple[int, str, str]:
    parsed = json_compact(value)
    if not isinstance(parsed, list):
        return (0, "", "")
    entries = [item for item in parsed if isinstance(item, dict)]
    if not entries:
        return (0, "", "")
    scopes = preview_items_fn(
        [str(item.get("scope") or "").strip() for item in entries if str(item.get("scope") or "").strip()]
    )
    triggers = preview_items_fn(
        [str(item.get("trigger") or "").strip() for item in entries if str(item.get("trigger") or "").strip()]
    )
    return (len(entries), scopes, triggers)

# Wrapper aliases kept for import stability and monkeypatchability at this module surface.
operator_workflow_detail_lines = _operator_workflow_detail_lines
operator_background_task_detail_lines = _operator_background_task_detail_lines
single_operator_detail_line = _single_operator_detail_line
