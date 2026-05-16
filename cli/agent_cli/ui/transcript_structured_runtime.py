from __future__ import annotations

from typing import Any

from cli.agent_cli.models import ActivityEvent, activity_code


def state_from_status(status: object) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"running", "in_progress", "pending"}:
        return "running"
    if normalized in {"success", "completed", "complete"}:
        return "completed"
    if normalized in {"error", "failed", "failure"}:
        return "error"
    if normalized in {"cancelled", "canceled"}:
        return "cancelled"
    return normalized or "info"


def command_group_key(command_text: str) -> str:
    tokens = str(command_text or "").strip().lower().split(maxsplit=1)
    if not tokens:
        return "command"
    token = tokens[0]
    if token in {"cat", "sed", "head", "tail", "less", "more", "awk"}:
        return "read"
    if token in {"rg", "grep", "ag", "fd", "find"}:
        return "search"
    if token in {"ls", "tree"}:
        return "list"
    if token in {"git", "wc", "stat", "file", "pwd"}:
        return "inspect"
    return "command"


def exploration_group_key(details: list[tuple[str, str]]) -> str:
    kinds = {
        str(kind or "").strip().lower() for kind, _subject in details if str(kind or "").strip()
    }
    if len(kinds) == 1:
        return next(iter(kinds))
    return "tool"


def exploration_summary(details: list[tuple[str, str]]) -> str:
    if not details:
        return ""
    kind, subject = details[0]
    return f"{_exploration_kind_label(kind)} {str(subject or '').strip()}".strip()


def _exploration_kind_label(kind: str) -> str:
    normalized = str(kind or "").strip().lower()
    if normalized == "read":
        return "Read"
    if normalized == "search":
        return "Search"
    if normalized == "list":
        return "List"
    if normalized:
        return normalized.capitalize()
    return "Tool"


def message_payload(
    *,
    name: str,
    text: str,
    state: str = "completed",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "text",
        "name": name,
        "state": state,
        "text": str(text or ""),
        "metadata": dict(metadata or {}),
    }


def reasoning_payload(text: str) -> dict[str, Any]:
    return {
        "type": "reasoning",
        "name": "reasoning",
        "state": "completed",
        "text": str(text or ""),
    }


def separator_payload(label: str) -> dict[str, Any]:
    return {
        "type": "separator",
        "name": "separator",
        "state": "info",
        "title": str(label or "").strip(),
    }


def activity_payload(event: ActivityEvent, *, detail_text: str | None = None) -> dict[str, Any]:
    code = activity_code(event)
    title = str(event.title or "").strip()
    detail = str(event.detail if detail_text is None else detail_text or "").strip()
    params = dict(event.params or {})
    group_key = _activity_group_key(code, event, params)
    return {
        "type": "activity",
        "name": code or str(event.kind or "activity").strip() or "activity",
        "kind": str(event.kind or "activity").strip() or "activity",
        "state": state_from_status(event.status),
        "title": title,
        "summary": _activity_summary(code, title, detail, params),
        "group_key": group_key,
        "input": params,
        "output": detail,
        "metadata": {
            "code": code,
            "status": str(event.status or "").strip(),
        },
    }


def todo_payload(
    *,
    todos: list[dict[str, Any]],
    source: str,
    state: str = "info",
) -> dict[str, Any]:
    return {
        "type": "tool",
        "name": "todo_list",
        "state": state,
        "title": "Todo List",
        "summary": "Todo List",
        "input": {"items": [dict(item) for item in todos]},
        "metadata": {"source": source},
    }


def command_execution_payload(
    *,
    command_text: str,
    raw_command_text: str = "",
    command_lines: list[str],
    output_lines: list[str],
    status_text: str,
    exit_code: object,
    source: str = "command_execution",
    cwd: object = None,
    duration_ms: object = None,
    process_id: object = None,
    output_truncated: bool = False,
    output_line_count: int | None = None,
) -> dict[str, Any]:
    state = state_from_status(status_text)
    if state == "completed":
        state = "completed"
    elif state != "error":
        state = "running"
    metadata: dict[str, Any] = {
        "source": source,
        "status": str(status_text or "").strip(),
        "exit_code": exit_code,
        "output_lines": list(output_lines),
        "output_truncated": bool(output_truncated),
    }
    cwd_text = str(cwd or "").strip()
    if cwd_text:
        metadata["cwd"] = cwd_text
    process_id_text = str(process_id or "").strip()
    if process_id_text:
        metadata["process_id"] = process_id_text
    if duration_ms not in {None, ""}:
        metadata["duration_ms"] = duration_ms
    if output_line_count is not None:
        metadata["output_line_count"] = int(output_line_count)
    summary_command = str(command_text or raw_command_text or "").strip()
    summary_prefix = "Ran" if state in {"completed", "error"} else "Running"
    return {
        "type": "tool",
        "name": "command_execution",
        "state": state,
        "title": "Ran command" if state in {"completed", "error"} else "Running command",
        "summary": f"{summary_prefix} {summary_command}".strip(),
        "group_key": command_group_key(summary_command),
        "input": {
            "command": str(raw_command_text or command_text or ""),
            "display_command": str(command_text or ""),
            "command_lines": list(command_lines),
        },
        "output": "\n".join(str(line) for line in output_lines),
        "metadata": metadata,
    }


def command_exploration_payload(
    *,
    details: list[tuple[str, str]],
    state: str,
) -> dict[str, Any]:
    normalized_details = [
        (str(kind or "").strip(), str(subject or "").strip()) for kind, subject in details
    ]
    return {
        "type": "tool",
        "name": "command_exploration",
        "state": state_from_status(state),
        "title": "Explored" if state_from_status(state) == "completed" else "Exploring",
        "summary": exploration_summary(normalized_details),
        "group_key": exploration_group_key(normalized_details),
        "input": {
            "details": [{"kind": kind, "subject": subject} for kind, subject in normalized_details]
        },
        "metadata": {"source": "command_execution"},
    }


def exploration_activity_payload(
    event: ActivityEvent,
    *,
    details: list[tuple[str, str]],
) -> dict[str, Any]:
    normalized_details = [
        (str(kind or "").strip(), str(subject or "").strip()) for kind, subject in details
    ]
    return {
        "type": "tool",
        "name": "command_exploration",
        "state": state_from_status(event.status),
        "title": "Explored" if state_from_status(event.status) == "completed" else "Exploring",
        "summary": exploration_summary(normalized_details),
        "group_key": exploration_group_key(normalized_details),
        "input": {
            "details": [{"kind": kind, "subject": subject} for kind, subject in normalized_details]
        },
        "metadata": {
            "source": "activity_event",
            "code": activity_code(event),
            "status": str(event.status or "").strip(),
        },
    }


def mcp_tool_payload(
    *,
    item: dict[str, object],
    invocation: str,
    detail: str,
    event_completed: bool,
    ok: bool,
) -> dict[str, Any]:
    arguments = item.get("arguments")
    state = "completed" if ok else ("error" if event_completed else "running")
    return {
        "type": "tool",
        "name": "mcp_tool_call",
        "state": state,
        "title": "Called tool" if event_completed else "Calling tool",
        "summary": str(invocation or "").strip() or "tool",
        "group_key": "tool_call",
        "input": {
            "invocation": str(invocation or ""),
            "arguments": dict(arguments) if isinstance(arguments, dict) else {},
        },
        "output": str(detail or ""),
        "metadata": {
            "server": str(item.get("server") or "local").strip() or "local",
            "tool_name": str(item.get("tool") or "").strip() or "tool",
            "status": str(item.get("status") or "").strip(),
        },
    }


def artifact_tool_payload(
    *,
    name: str,
    title: str,
    state: str,
    subject: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    group_key = "image" if name in {"view_image", "input_image_output"} else "document"
    return {
        "type": "tool",
        "name": name,
        "state": "completed",
        "title": title,
        "summary": " ".join(
            part for part in (str(title or "").strip(), str(subject or "").strip()) if part
        ),
        "group_key": group_key,
        "input": {"subject": subject},
        "metadata": {"state": state, **dict(metadata or {})},
    }


def _activity_group_key(code: str, event: ActivityEvent, params: dict[str, Any]) -> str:
    del event
    if code == "web.search":
        backend = str(params.get("backend") or "").strip().lower()
        if bool(params.get("provider_native")) or backend == "native":
            return "native_web_search"
        if backend == "local":
            return "local_web_search"
        return "web_search"
    if code.endswith(".find"):
        return "web_find"
    if code in {"dir.list", "file.list"}:
        return "list"
    if code in {"dir.search", "file.search"}:
        return "search"
    if code == "file.read":
        return "read"
    if code == "image.view":
        return "image"
    if code == "command.run":
        return "tool"
    return ""


def _activity_summary(code: str, title: str, detail: str, params: dict[str, Any]) -> str:
    if code == "web.search":
        query_text = str(params.get("query") or "").strip()
        if query_text:
            return query_text
    if code in {"dir.search", "file.search"}:
        query_text = str(params.get("query") or params.get("pattern") or "").strip()
        path_text = str(params.get("path") or params.get("dir_path") or "").strip()
        if query_text and path_text:
            return f"{query_text} in {path_text}"
        if query_text:
            return query_text
    if code in {"dir.list", "file.list", "file.read", "image.view"}:
        subject = str(params.get("path") or params.get("dir_path") or "").strip()
        if subject:
            return subject
    return detail.splitlines()[0].strip() if detail else title
