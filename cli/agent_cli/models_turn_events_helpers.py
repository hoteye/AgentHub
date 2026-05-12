from __future__ import annotations

import json
from typing import Any

from cli.agent_cli.models import ResponseInputItem, ToolEvent


def latest_open_todo_list_item(item_events: list[dict[str, Any]]) -> dict[str, Any] | None:
    running: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw_event in list(item_events or []):
        if not isinstance(raw_event, dict):
            continue
        event_type = str(raw_event.get("type") or "").strip()
        if event_type not in {"item.started", "item.updated", "item.completed"}:
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "todo_list":
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        if event_type == "item.completed":
            running.pop(item_id, None)
            order = [candidate for candidate in order if candidate != item_id]
            continue
        running[item_id] = dict(item)
        order = [candidate for candidate in order if candidate != item_id]
        order.append(item_id)
    for item_id in reversed(order):
        item = running.get(item_id)
        if item is not None:
            return dict(item)
    return None


def completed_todo_list_turn_events(item_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    running: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw_event in list(item_events or []):
        if not isinstance(raw_event, dict):
            continue
        event_type = str(raw_event.get("type") or "").strip()
        if event_type not in {"item.started", "item.updated", "item.completed"}:
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "todo_list":
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        if event_type == "item.completed":
            running.pop(item_id, None)
            order = [candidate for candidate in order if candidate != item_id]
            continue
        running[item_id] = dict(item)
        order = [candidate for candidate in order if candidate != item_id]
        order.append(item_id)
    for item_id in order:
        item = running.get(item_id)
        if item is None:
            continue
        completed.append(
            {
                "type": "item.completed",
                "item": dict(item),
            }
        )
    return completed


def generic_tool_error_message(tool_event: ToolEvent) -> str:
    payload = dict(tool_event.payload or {})
    for key in ("error", "stderr", "message"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return str(tool_event.summary or tool_event.name or "tool failed").strip()


def response_item_tool_key(item: dict[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("type") or "").strip().lower(),
        str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip(),
    )


def reasoning_text_from_turn_event_item(item: dict[str, Any]) -> str:
    text = reasoning_explicit_text_from_turn_event_item(item)
    if text:
        return text
    return reasoning_summary_text_from_turn_event_item(item)


def reasoning_summary_text_from_turn_event_item(item: dict[str, Any]) -> str:
    summary = item.get("summary")
    if not isinstance(summary, list):
        return ""
    parts: list[str] = []
    for entry in summary:
        if isinstance(entry, dict):
            entry_text = str(entry.get("text") or "").strip()
        else:
            entry_text = str(entry).strip()
        if entry_text:
            parts.append(entry_text)
    if not parts:
        return ""
    return "\n\n".join(parts)


def reasoning_explicit_text_from_turn_event_item(item: dict[str, Any]) -> str:
    text = str(item.get("text") or "").strip()
    if text:
        return text
    content = item.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for entry in list(content or []):
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        if entry_type not in {"reasoning", "text", "input_text", "output_text"}:
            continue
        entry_text = str(entry.get("text") or "").strip()
        if entry_text:
            parts.append(entry_text)
    return "\n\n".join(parts).strip()


def reasoning_turn_event_key(item: dict[str, Any]) -> tuple[str, str, str]:
    text = reasoning_text_from_turn_event_item(item)
    summary = item.get("summary")
    try:
        summary_key = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    except TypeError:
        summary_key = str(summary)
    encrypted_content = str(item.get("encrypted_content") or "").strip()
    return (text, summary_key, encrypted_content)


def reasoning_input_item_from_turn_event_item(item: dict[str, Any]) -> dict[str, Any] | None:
    text = reasoning_text_from_turn_event_item(item)
    if not text:
        return None
    extra: dict[str, Any] = {}
    provider_item_id = str(item.get("provider_item_id") or "").strip()
    if provider_item_id:
        extra["id"] = provider_item_id
    status = item.get("status")
    if status not in (None, ""):
        extra["status"] = status
    summary = item.get("summary")
    if summary not in (None, ""):
        extra["summary"] = summary
    encrypted_content = item.get("encrypted_content")
    if encrypted_content not in (None, ""):
        extra["encrypted_content"] = encrypted_content
    return ResponseInputItem(
        item_type="reasoning",
        content=[{"type": "reasoning", "text": text}],
        extra=extra,
    ).to_dict()


def reasoning_content_has_text(content: Any) -> bool:
    if not isinstance(content, list):
        return False
    for entry in content:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        if entry_type not in {"reasoning", "text", "input_text", "output_text"}:
            continue
        if str(entry.get("text") or "").strip():
            return True
    return False


def _reasoning_replay_guard_diagnostic(
    *,
    source: str,
    reason: str,
    summary_present: bool,
    explicit_text_present: bool,
) -> dict[str, Any]:
    return {
        "item_type": "reasoning",
        "source": str(source or "").strip() or "shared_replay",
        "retention": "stripped",
        "guard": str(reason or "").strip() or "reasoning_replay_guard",
        "summary_present": bool(summary_present),
        "content_present": bool(explicit_text_present),
        "detail": (
            "shared replay stripped previous-turn reasoning because encrypted_content is missing"
        ),
    }


def shared_replay_reasoning_projection_from_parts(
    *,
    explicit_text: str,
    summary: Any,
    encrypted_content: Any,
    replay_content: list[dict[str, Any]] | None,
    source: str,
    content_present: bool,
) -> dict[str, Any]:
    summary_present = summary not in (None, "", [])
    normalized_encrypted_content = str(encrypted_content or "").strip()
    if (
        not explicit_text
        and not summary_present
        and not normalized_encrypted_content
        and not content_present
    ):
        return {"input_item": None, "diagnostic": None}
    if not normalized_encrypted_content:
        return {
            "input_item": None,
            "diagnostic": _reasoning_replay_guard_diagnostic(
                source=source,
                reason="missing_encrypted_content",
                summary_present=summary_present,
                explicit_text_present=bool(content_present),
            ),
        }
    replay_item: dict[str, Any] = {
        "type": "reasoning",
        "encrypted_content": normalized_encrypted_content,
        "summary": summary if summary_present else [],
    }
    if replay_content:
        replay_item["content"] = list(replay_content)
    return {"input_item": replay_item, "diagnostic": None}


def reasoning_replay_projection_from_turn_event_item(item: dict[str, Any]) -> dict[str, Any]:
    explicit_text = reasoning_explicit_text_from_turn_event_item(item)
    summary = item.get("summary")
    projection = shared_replay_reasoning_projection_from_parts(
        explicit_text=explicit_text,
        summary=summary,
        encrypted_content=item.get("encrypted_content"),
        replay_content=([{"type": "reasoning", "text": explicit_text}] if explicit_text else None),
        source="turn_event_replay",
        content_present=bool(explicit_text),
    )
    projected = projection.get("input_item")
    if not isinstance(projected, dict):
        return projection
    return {
        "input_item": ResponseInputItem.from_dict(projected).to_dict(),
        "diagnostic": projection.get("diagnostic"),
    }


def rebase_turn_item_events(
    events: list[dict[str, Any]],
    *,
    start_index: int,
) -> tuple[list[dict[str, Any]], int]:
    mapping: dict[str, str] = {}
    next_index = int(start_index)
    rebased: list[dict[str, Any]] = []
    for event in list(events or []):
        if not isinstance(event, dict):
            continue
        copied = dict(event)
        item = copied.get("item")
        if not isinstance(item, dict):
            rebased.append(copied)
            continue
        item_copy = dict(item)
        original_id = str(item_copy.get("id") or "").strip()
        if original_id:
            replacement = mapping.get(original_id)
            if replacement is None:
                replacement = f"item_{next_index}"
                mapping[original_id] = replacement
                next_index += 1
            item_copy["id"] = replacement
        copied["item"] = item_copy
        rebased.append(copied)
    return rebased, next_index


def shell_aggregated_output(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    stdout = str(payload.get("stdout") or payload.get("output_text") or "")
    stderr = str(payload.get("stderr") or "")
    if stdout:
        chunks.append(stdout)
    if stderr:
        chunks.append(stderr)
    if not chunks:
        return ""
    return "".join(
        chunk if index == 0 or chunks[index - 1].endswith("\n") else "\n" + chunk
        for index, chunk in enumerate(chunks)
    )


def shell_exit_code(payload: dict[str, Any]) -> int | None:
    value = payload.get("returncode")
    if value is None:
        value = payload.get("exit_code")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def shell_status(tool_event: ToolEvent) -> str:
    if str(tool_event.name or "").strip().lower() == "shell_approval_requested":
        return "declined"
    return "completed" if tool_event.ok else "failed"


def turn_event_content_types(content: Any) -> set[str]:
    if not isinstance(content, list):
        return set()
    return {
        str(entry.get("type") or "").strip().lower() for entry in content if isinstance(entry, dict)
    }


def turn_event_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for entry in content:
        if not isinstance(entry, dict):
            continue
        block_type = str(entry.get("type") or "").strip().lower()
        if block_type in {"output_text", "input_text", "text", "reasoning"}:
            text = str(entry.get("text") or "")
            if text:
                parts.append(text)
    return "".join(parts)


def turn_event_usage_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def tool_event_is_shell(tool_event: ToolEvent) -> bool:
    normalized = str(tool_event.name or "").strip().lower()
    return normalized.startswith("shell") or normalized in {"exec_command", "write_stdin"}
