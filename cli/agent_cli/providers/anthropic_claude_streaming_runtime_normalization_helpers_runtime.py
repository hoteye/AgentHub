from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli.providers import (
    anthropic_claude_streaming_runtime_projection_helpers_runtime as projection_helpers,
)
from cli.agent_cli.providers import anthropic_claude_streaming_runtime_pure_helpers_runtime as pure_helpers


def recover_partial_stream_content(
    *,
    open_blocks: Dict[int, Dict[str, Any]],
    response_content: List[Any],
    allow_tools: bool,
    message_id: str,
    emit_turn_event_fn: Callable[[Dict[str, Any]], None],
) -> int:
    recovered_message_count = 0
    for index in sorted(open_blocks):
        state = open_blocks.get(index)
        if not isinstance(state, dict):
            continue
        block_type = pure_helpers.stream_string(state.get("type"))
        if block_type == "text":
            text = str(state.get("text") or "").strip()
            if not text:
                continue
            response_content.append({"type": "text", "text": text})
            recovered_message_count += 1
            emit_turn_event_fn(
                projection_helpers.stream_agent_message_event(
                    event_type="item.completed",
                    item_id=pure_helpers.stream_message_item_id(message_id, index),
                    text=text,
                )
            )
            continue
        if block_type in {"thinking", "reasoning"}:
            text = str(state.get("text") or "").strip()
            if not text:
                continue
            response_content.append({"type": block_type, "text": text})
            emit_turn_event_fn(
                projection_helpers.stream_reasoning_event(
                    event_type="item.completed",
                    item_id=pure_helpers.stream_message_item_id(message_id, index),
                    text=text,
                )
            )
            continue
        if block_type != "tool_use":
            continue
        arguments = pure_helpers.stream_parse_tool_input(state)
        call_id = pure_helpers.stream_string(state.get("id"))
        name = pure_helpers.stream_string(state.get("name"))
        if arguments is None or not name:
            continue
        response_content.append(
            {
                "type": "tool_use",
                "id": call_id,
                "name": name,
                "input": arguments,
            }
        )
        emit_turn_event_fn(
            projection_helpers.stream_function_call_completed_event(
                call_id=call_id,
                name=name,
                arguments=arguments,
            )
        )
        if allow_tools and name and call_id:
            continue
    return recovered_message_count


__all__ = ["recover_partial_stream_content"]
