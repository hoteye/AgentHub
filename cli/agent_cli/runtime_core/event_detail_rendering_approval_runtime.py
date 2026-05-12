from __future__ import annotations

from typing import Any

from cli.agent_cli import approval_contract_runtime


def _continuation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    continuation = payload.get("continuation")
    return dict(continuation) if isinstance(continuation, dict) else {}


def _continuation_status_line(payload: dict[str, Any]) -> str:
    continuation = _continuation_payload(payload)
    status = str(continuation.get("continuation_status") or "").strip()
    if not status:
        return ""
    if status == "completed":
        return "continuation=completed"
    if status == "tool_result_built":
        return "continuation=ready"
    if status == "stale_pending":
        return "continuation=stale_pending"
    if status == "pending":
        return "continuation=pending"
    return f"continuation={status}"


def _structured_write_change(payload: dict[str, Any]) -> dict[str, Any]:
    changes = payload.get("changes")
    if not isinstance(changes, list) or not changes:
        return {}
    first = changes[0]
    return dict(first) if isinstance(first, dict) else {}


def apply_patch_activity(payload: dict[str, Any], *, ok: bool) -> str:
    if not ok:
        return str(payload.get("error") or "patch apply failed").strip()
    if str(payload.get("request_kind") or "").strip().lower() == "structured_write":
        change = _structured_write_change(payload)
        path = str(change.get("path") or payload.get("file_path") or "").strip()
        write_mode = str(change.get("write_mode") or "").strip().lower()
        parts = [f"files={int(payload.get('file_count') or 0)}"]
        if path:
            parts.append(path)
        if write_mode:
            parts.append(f"write_mode={write_mode}")
        return "\n".join(parts)
    parts = [f"files={int(payload.get('file_count') or 0)}"]
    added = int(payload.get("added_count") or 0)
    updated = int(payload.get("updated_count") or 0)
    deleted = int(payload.get("deleted_count") or 0)
    moved = int(payload.get("moved_count") or 0)
    if added:
        parts.append(f"add={added}")
    if updated:
        parts.append(f"update={updated}")
    if deleted:
        parts.append(f"delete={deleted}")
    if moved:
        parts.append(f"move={moved}")
    parts.extend(
        str(item.get("path") or "").strip()
        for item in (payload.get("changes") or [])[:4]
        if str(item.get("path") or "").strip()
    )
    return "\n".join(parts)


def patch_approval_requested_activity(payload: dict[str, Any], *, ok: bool) -> str:
    if not ok:
        return str(payload.get("error") or "patch approval request failed").strip()
    parts = [str(payload.get("approval_id") or "-")]
    file_count = payload.get("file_count")
    if file_count is not None:
        parts.append(f"files={int(file_count)}")
    commands = approval_contract_runtime.approval_option_commands(
        str(payload.get("approval_id") or "").strip(),
        payload.get("available_decisions"),
    )
    parts.extend(commands)
    parts.extend(change_summary_lines(payload.get("changes"), limit=4))
    return "\n".join(parts)


def generic_approval_requested_activity(payload: dict[str, Any], *, ok: bool) -> str:
    if not ok:
        return str(payload.get("error") or "approval request failed").strip()
    parts = [str(payload.get("approval_id") or "-")]
    task = str(payload.get("task") or "").strip()
    if task:
        parts.append(task)
    else:
        summary = str(payload.get("summary") or payload.get("summary_text") or "").strip()
        if summary:
            parts.append(summary)
    commands = approval_contract_runtime.approval_option_commands(
        str(payload.get("approval_id") or "").strip(),
        payload.get("available_decisions"),
    )
    parts.extend(commands)
    return "\n".join(parts)


def approval_list_activity(payload: dict[str, Any], *, ok: bool) -> str:
    if not ok:
        return str(payload.get("error") or "approval list failed").strip()
    parts = [f"count={int(payload.get('count') or 0)}"]
    status = str(payload.get("status") or "").strip()
    if status:
        parts.append(f"status={status}")
    parts.extend(
        " | ".join(
            segment
            for segment in [
                str(item.get("approval_id") or "").strip(),
                str(item.get("status") or "").strip(),
                str(item.get("action_type") or "").strip(),
                str(item.get("continuation_status") or "").strip(),
                str(item.get("summary") or "").strip(),
            ]
            if segment
        )
        for item in (payload.get("approvals") or [])[:6]
    )
    return "\n".join(parts)


def approval_decision_activity(payload: dict[str, Any], *, ok: bool) -> str:
    if not ok:
        return str(payload.get("error") or "approval decision failed").strip()
    parts = [str(payload.get("approval_id") or "-"), f"status={payload.get('status') or '-'}"]
    if payload.get("decision_type"):
        parts.append(f"decision={payload['decision_type']}")
    if payload.get("action_type"):
        parts.append(f"action_type={payload['action_type']}")
    if payload.get("command"):
        parts.append(f"command={payload['command']}")
    if payload.get("decision_by"):
        parts.append(f"by={payload['decision_by']}")
    if payload.get("decision_note"):
        parts.append(f"note={payload['decision_note']}")
    continuation_line = _continuation_status_line(payload)
    if continuation_line:
        parts.append(continuation_line)
    return "\n".join(parts)


def apply_patch_detail(payload: dict[str, Any], *, ok: bool) -> str:
    if not ok:
        return str(payload.get("error") or "patch apply failed").strip()
    if str(payload.get("request_kind") or "").strip().lower() == "structured_write":
        change = _structured_write_change(payload)
        parts = [
            f"file_count={int(payload.get('file_count') or 0)}",
            f"path={change.get('path') or payload.get('file_path') or '-'}",
        ]
        write_mode = str(change.get("write_mode") or "").strip()
        if write_mode:
            parts.append(f"write_mode={write_mode}")
        source_tool_name = str(payload.get("source_tool_name") or payload.get("function_call_name") or "").strip()
        if source_tool_name:
            parts.append(f"source_tool_name={source_tool_name}")
        return "\n".join(parts)
    if str(payload.get("request_kind") or "").strip().lower() == "structured_edit":
        change = ((payload.get("changes") or [{}])[0] if isinstance(payload.get("changes"), list) and payload.get("changes") else {})
        parts = [
            f"file_count={int(payload.get('file_count') or 0)}",
            f"path={change.get('path') or payload.get('file_path') or '-'}",
        ]
        match_count = change.get("match_count")
        if match_count is not None:
            parts.append(f"match_count={int(match_count or 0)}")
        if "replace_all" in change:
            parts.append(f"replace_all={bool(change.get('replace_all'))}")
        source_tool_name = str(payload.get("source_tool_name") or payload.get("function_call_name") or "").strip()
        if source_tool_name:
            parts.append(f"source_tool_name={source_tool_name}")
        return "\n".join(parts)
    parts = [
        f"file_count={int(payload.get('file_count') or 0)}",
        f"added_count={int(payload.get('added_count') or 0)}",
        f"updated_count={int(payload.get('updated_count') or 0)}",
        f"deleted_count={int(payload.get('deleted_count') or 0)}",
        f"moved_count={int(payload.get('moved_count') or 0)}",
    ]
    parts.extend(change_summary_lines(payload.get("changes"), limit=10))
    return "\n".join(parts)


def approval_detail(event_name: str, payload: dict[str, Any], *, ok: bool) -> str:
    if event_name == "patch_approval_requested":
        if not ok:
            return str(payload.get("error") or "patch approval request failed").strip()
        parts = [
            f"approval_id={payload.get('approval_id') or '-'}",
            f"file_count={int(payload.get('file_count') or 0)}",
        ]
        commands = approval_contract_runtime.approval_option_commands(
            str(payload.get("approval_id") or "").strip(),
            payload.get("available_decisions"),
        )
        parts.extend(commands)
        parts.extend(change_summary_lines(payload.get("changes"), limit=10))
        return "\n".join(parts)
    if event_name == "approval_list":
        if not ok:
            return str(payload.get("error") or "approval list failed").strip()
        parts = [f"count={int(payload.get('count') or 0)}"]
        if payload.get("status"):
            parts.append(f"status={payload['status']}")
        for item in (payload.get("approvals") or [])[:10]:
            row = [f"approval_id={item.get('approval_id')}", f"status={item.get('status')}"]
            if item.get("action_type"):
                row.append(f"action_type={item.get('action_type')}")
            if item.get("continuation_status"):
                row.append(f"continuation_status={item.get('continuation_status')}")
            if item.get("continuation_stale"):
                row.append("continuation_stale=true")
            if item.get("summary"):
                row.append(f"summary={item.get('summary')}")
            parts.append(" | ".join(row))
        return "\n".join(parts)
    if event_name == "approval_decision":
        if not ok:
            return str(payload.get("error") or "approval decision failed").strip()
        parts = [
            f"approval_id={payload.get('approval_id') or '-'}",
            f"status={payload.get('status') or '-'}",
        ]
        if payload.get("decision_type"):
            parts.append(f"decision_type={payload['decision_type']}")
        if payload.get("action_type"):
            parts.append(f"action_type={payload['action_type']}")
        if payload.get("decision_by"):
            parts.append(f"decision_by={payload['decision_by']}")
        if payload.get("decision_note"):
            parts.append(f"decision_note={payload['decision_note']}")
        continuation_line = _continuation_status_line(payload)
        if continuation_line:
            parts.append(continuation_line)
        return "\n".join(parts)
    if event_name.endswith("_approval_requested"):
        if not ok:
            return str(payload.get("error") or "approval request failed").strip()
        parts = [f"approval_id={payload.get('approval_id') or '-'}"]
        summary = str(payload.get("summary") or payload.get("summary_text") or "").strip()
        task = str(payload.get("task") or "").strip()
        if summary:
            parts.append(f"summary={summary}")
        if task:
            parts.append(f"task={task}")
        if payload.get("provider"):
            parts.append(f"provider={payload['provider']}")
        if payload.get("model"):
            parts.append(f"model={payload['model']}")
        commands = approval_contract_runtime.approval_option_commands(
            str(payload.get("approval_id") or "").strip(),
            payload.get("available_decisions"),
        )
        parts.extend(commands)
        return "\n".join(parts)
    return ""


def change_summary_lines(changes: Any, *, limit: int) -> list[str]:
    lines: list[str] = []
    for item in (changes or [])[:limit]:
        change_type = str(item.get("change_type") or "update")
        path = str(item.get("path") or "").strip()
        moved_from = str(item.get("moved_from") or "").strip()
        line = f"{change_type} | {path}" if path else change_type
        if moved_from:
            line += f" | from={moved_from}"
        lines.append(line)
    return lines
