from __future__ import annotations

from typing import Any

from cli.agent_cli.providers.adapters.openai_responses_stream import stream_index_value

PARTIAL_TOOL_CALL_ITEM_TYPES = {
    "function_call",
    "custom_tool_call",
    "shell_call",
    "local_shell_call",
}


def message_buffer_key(event: Any) -> str:
    return f"message_{stream_index_value(event)}"


def reasoning_buffer_key(event: Any) -> str:
    return f"reasoning_{stream_index_value(event)}"


def pending_tool_call_key(
    event: Any,
    *,
    raw_item: dict[str, Any] | None = None,
    item_id: str = "",
    item_type: str = "",
) -> str:
    provider_item_id = str(item_id or (raw_item or {}).get("id") or "").strip()
    if provider_item_id:
        return f"id:{provider_item_id}"
    output_index = getattr(event, "output_index", None)
    normalized_type = str(item_type or (raw_item or {}).get("type") or "").strip().lower() or "tool_call"
    call_id = str((raw_item or {}).get("call_id") or "").strip()
    if output_index is not None:
        if call_id:
            return f"output:{output_index}:{normalized_type}:{call_id}"
        return f"output:{output_index}:{normalized_type}"
    if call_id:
        return f"call:{normalized_type}:{call_id}"
    return ""


def resolved_output_item_id(
    raw_item: dict[str, Any],
    *,
    response_item_count: int,
    buffered_item_id: str = "",
) -> str:
    resolved_buffered_id = str(buffered_item_id or "").strip()
    if resolved_buffered_id:
        return resolved_buffered_id
    return str(raw_item.get("id") or f"stream_item_{response_item_count - 1}").strip()


__all__ = [
    "PARTIAL_TOOL_CALL_ITEM_TYPES",
    "message_buffer_key",
    "pending_tool_call_key",
    "reasoning_buffer_key",
    "resolved_output_item_id",
]
