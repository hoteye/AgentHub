from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TextIO

from cli.agent_cli.models import ActivityEvent, ToolEvent

STREAM_TOOL_ITEM_TYPES: frozenset[str] = frozenset(
    {
        "command_execution",
        "mcp_tool_call",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "shell_call",
        "shell_call_output",
        "local_shell_call",
        "local_shell_call_output",
    }
)


def tool_event_to_dict(item: ToolEvent) -> dict[str, Any]:
    return {
        "name": item.name,
        "ok": item.ok,
        "summary": item.summary,
        "payload": dict(item.payload or {}),
    }


def activity_event_to_dict(item: ActivityEvent) -> dict[str, Any]:
    return {
        "title": item.title,
        "status": item.status,
        "detail": item.detail,
        "kind": item.kind,
    }


def emit_json_line(output_stream: TextIO, payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), file=output_stream, flush=True)


def emit_reference_jsonl_event(
    output_stream: TextIO,
    payload: dict[str, Any],
    *,
    request_id: str | None = None,
    codex_jsonl: bool = False,
    emit_json_line_fn: Callable[[TextIO, dict[str, Any]], None],
) -> None:
    line = dict(payload or {})
    if not codex_jsonl:
        line.setdefault("event_type", stream_json_event_type(line))
    if request_id is not None and not codex_jsonl:
        line["id"] = request_id
    emit_json_line_fn(output_stream, line)


def stream_json_event_type(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return "error"
    payload_type = str(payload.get("type") or "").strip().lower()
    if payload_type == "error":
        return "error"
    if payload_type.startswith("thread.") or payload_type.startswith("session."):
        return "session"
    if payload_type.startswith("turn."):
        return "turn"
    if payload_type.startswith("item."):
        item = payload.get("item")
        if isinstance(item, dict):
            item_type = str(item.get("type") or "").strip().lower()
            if item_type in STREAM_TOOL_ITEM_TYPES:
                return "tool"
        return "turn"
    return "turn"
