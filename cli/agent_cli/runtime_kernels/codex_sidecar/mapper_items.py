from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar.mapper_normalization import (
    _field,
    _id_from_item,
    _list,
    _mapping,
    _snake_case,
    _status,
    _text,
)


def _input_text_from_content(value: Any) -> str:
    parts: list[str] = []
    for entry in _list(value):
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                parts.append(text)
            continue
        item = _mapping(entry)
        entry_type = _text(item.get("type"))
        if entry_type in {"text", "input_text", "inputText"}:
            text = str(_field(item, "text", "value") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _text(_field(value, "text", "value"))
    parts: list[str] = []
    for entry in _list(value):
        if isinstance(entry, str):
            text = entry.strip()
        elif isinstance(entry, dict):
            text = _text(_field(entry, "text", "value"))
        else:
            text = ""
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _reasoning_text(item: dict[str, Any]) -> str:
    summary_parts = [_text(part) for part in _list(item.get("summary")) if _text(part)]
    content_parts = [_text(part) for part in _list(item.get("content")) if _text(part)]
    return "\n\n".join([*summary_parts, *content_parts]).strip()


def _mcp_result_text(result: dict[str, Any]) -> str:
    parts: list[str] = []
    for entry in _list(result.get("content")):
        if isinstance(entry, str):
            text = entry.strip()
        else:
            text = _text(_field(_mapping(entry), "text", "value"))
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def map_thread_item(item: dict[str, Any]) -> dict[str, Any]:
    raw = _mapping(item)
    raw_type = _text(_field(raw, "type", "itemType", "item_type"))
    item_type = _snake_case(raw_type)
    if item_type == "agent_message":
        mapped: dict[str, Any] = {
            "id": _id_from_item(raw),
            "type": "agent_message",
            "text": str(raw.get("text") or ""),
        }
        phase = _status(raw.get("phase"))
        if phase:
            mapped["phase"] = phase
        citation = _mapping(_field(raw, "memoryCitation", "memory_citation"))
        if citation:
            mapped["memory_citation"] = citation
        return mapped
    if item_type == "reasoning":
        mapped = {"id": _id_from_item(raw), "type": "reasoning", "text": _reasoning_text(raw)}
        summary = _list(raw.get("summary"))
        content = _list(raw.get("content"))
        if summary:
            mapped["summary"] = [_text(part) for part in summary if _text(part)]
        if content:
            mapped["content"] = [_text(part) for part in content if _text(part)]
        return mapped
    if item_type == "command_execution":
        mapped = {
            "id": _id_from_item(raw),
            "type": "command_execution",
            "command": str(raw.get("command") or ""),
            "cwd": str(raw.get("cwd") or ""),
            "process_id": _text(_field(raw, "processId", "process_id")),
            "source": _status(raw.get("source")),
            "status": _status(raw.get("status"), default="in_progress"),
            "command_actions": _list(_field(raw, "commandActions", "command_actions")),
            "aggregated_output": str(_field(raw, "aggregatedOutput", "aggregated_output") or ""),
            "exit_code": _field(raw, "exitCode", "exit_code"),
            "duration_ms": _field(raw, "durationMs", "duration_ms"),
        }
        return {key: value for key, value in mapped.items() if value not in (None, "")}
    if item_type == "mcp_tool_call":
        result = _mapping(raw.get("result"))
        error = _mapping(raw.get("error"))
        mapped = {
            "id": _id_from_item(raw),
            "type": "mcp_tool_call",
            "server": str(raw.get("server") or ""),
            "tool": str(raw.get("tool") or ""),
            "status": _status(raw.get("status"), default="completed"),
            "arguments": raw.get("arguments"),
            "result": result or None,
            "error": error or None,
            "duration_ms": _field(raw, "durationMs", "duration_ms"),
        }
        result_text = _mcp_result_text(result)
        if result_text:
            mapped["summary"] = result_text
        return mapped
    if item_type == "dynamic_tool_call":
        result_text = _content_text(_field(raw, "contentItems", "content_items"))
        mapped = {
            "id": _id_from_item(raw),
            "type": "mcp_tool_call",
            "server": _text(raw.get("namespace")) or "dynamic",
            "tool": str(raw.get("tool") or ""),
            "status": _status(raw.get("status"), default="completed"),
            "arguments": raw.get("arguments"),
            "result": (
                {"content": [{"type": "text", "text": result_text}]} if result_text else None
            ),
            "error": None if raw.get("success") is not False else {"message": "tool failed"},
            "duration_ms": _field(raw, "durationMs", "duration_ms"),
        }
        return mapped
    if item_type == "web_search":
        query = str(raw.get("query") or "")
        return {
            "id": _id_from_item(raw),
            "type": "web_search_call",
            "query": query,
            "action": raw.get("action") if isinstance(raw.get("action"), dict) else None,
            "status": "completed",
            "search_phase": "search_results_received",
        }
    if item_type == "plan":
        text = str(raw.get("text") or "").strip()
        return {
            "id": _id_from_item(raw),
            "type": "reasoning",
            "text": text,
            "source_type": "plan",
        }
    if item_type == "user_message":
        return {
            "id": _id_from_item(raw),
            "type": "user_message",
            "text": _input_text_from_content(raw.get("content")),
        }
    if item_type == "context_compaction":
        return {
            "id": _id_from_item(raw),
            "type": "reasoning",
            "text": "Context compacted.",
            "source_type": "context_compaction",
        }
    if item_type:
        mapped = {"id": _id_from_item(raw), "type": item_type}
        mapped.update({key: value for key, value in raw.items() if key not in mapped})
        return mapped
    return {}
