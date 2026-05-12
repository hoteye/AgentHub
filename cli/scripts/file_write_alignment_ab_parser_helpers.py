from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _parse_agenthub_turn(payload: dict[str, Any]) -> dict[str, Any]:
    tool_events = [dict(item) for item in list(payload.get("tool_events") or []) if isinstance(item, dict)]
    provider_tool_names: list[str] = []
    function_call_names: list[str] = []
    source_tool_names: list[str] = []
    for event in tool_events:
        event_payload = dict(event.get("payload") or {})
        raw_item = dict(event_payload.get("provider_raw_item") or {})
        raw_name = str(raw_item.get("name") or "").strip()
        if raw_name:
            provider_tool_names.append(raw_name)
        function_call_name = str(event_payload.get("function_call_name") or "").strip()
        if function_call_name:
            function_call_names.append(function_call_name)
        source_tool_name = str(event_payload.get("source_tool_name") or "").strip()
        if source_tool_name:
            source_tool_names.append(source_tool_name)
    return {
        "assistant_text": str(payload.get("assistant_text") or ""),
        "tool_event_names": [str(item.get("name") or "") for item in tool_events],
        "provider_tool_names": provider_tool_names,
        "function_call_names": function_call_names,
        "source_tool_names": source_tool_names,
    }


def _parse_agenthub_request_tool_names(log_dir: Path) -> list[str]:
    path = log_dir / "llm_io.jsonl"
    if not path.exists():
        return []
    names: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if str(record.get("stage") or "") != "anthropic_messages.request_raw":
            continue
        request = dict(record.get("payload") or {}).get("request") or {}
        for tool in list(request.get("tools") or []):
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("name") or "").strip()
            if not name or name in seen:
                continue
            names.append(name)
            seen.add(name)
    return names


def _parse_codex_stdout(stdout_text: str, last_message_path: Path) -> dict[str, Any]:
    item_types: list[str] = []
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        item = event.get("item")
        if isinstance(item, dict):
            item_type = str(item.get("type") or "").strip()
            if item_type:
                item_types.append(item_type)
    assistant_text = last_message_path.read_text(encoding="utf-8").strip() if last_message_path.exists() else ""
    return {
        "assistant_text": assistant_text,
        "item_types": item_types,
        "tool_like_items": [item for item in item_types if item not in {"agent_message"}],
    }


def _parse_claude_stream(stdout_text: str) -> dict[str, Any]:
    tool_use_names: list[str] = []
    assistant_text = ""
    system_tools: list[str] = []
    session_id = ""
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        record = json.loads(line)
        record_type = str(record.get("type") or "").strip()
        if record_type == "system":
            session_id = str(record.get("session_id") or session_id)
            for name in list(record.get("tools") or []):
                text = str(name or "").strip()
                if text:
                    system_tools.append(text)
        elif record_type == "assistant":
            session_id = str(record.get("session_id") or session_id)
            message = dict(record.get("message") or {})
            content = list(message.get("content") or [])
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type") or "").strip()
                if block_type == "tool_use":
                    name = str(block.get("name") or "").strip()
                    if name:
                        tool_use_names.append(name)
                elif block_type == "text":
                    text = str(block.get("text") or "").strip()
                    if text:
                        assistant_text = text
        elif record_type == "result":
            session_id = str(record.get("session_id") or session_id)
            result_text = str(record.get("result") or "").strip()
            if result_text:
                assistant_text = result_text
    return {
        "assistant_text": assistant_text,
        "tool_use_names": tool_use_names,
        "system_tools": system_tools,
        "session_id": session_id,
    }
