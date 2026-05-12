from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.providers import (
    anthropic_claude_streaming_runtime_projection_helpers_runtime as projection_helpers,
)
from cli.agent_cli.providers import anthropic_claude_streaming_runtime_pure_helpers_runtime as pure_helpers


def _event_result(message_id: str, first_tool_ms: Optional[int]) -> Dict[str, Any]:
    return {
        "message_id": message_id,
        "first_tool_ms": first_tool_ms,
        "streamed_message_count_delta": 0,
        "early_response": None,
        "should_break": False,
    }


def _content_block_state(index: int, block: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": pure_helpers.stream_string(block.get("type")),
        "index": index,
        "id": pure_helpers.stream_string(block.get("id")),
        "name": pure_helpers.stream_string(block.get("name")),
        "text": str(block.get("text") or ""),
        "input": block.get("input") if isinstance(block.get("input"), dict) else None,
        "input_buffer": "",
    }


def _handle_message_start(event: Any, *, message_id: str, first_tool_ms: Optional[int]) -> Dict[str, Any]:
    result = _event_result(message_id, first_tool_ms)
    message_payload = pure_helpers.stream_dict_payload(pure_helpers.stream_value(event, "message"))
    result["message_id"] = pure_helpers.stream_string(message_payload.get("id")) or message_id
    return result


def _handle_content_block_start(
    event: Any,
    *,
    message_id: str,
    open_blocks: Dict[int, Dict[str, Any]],
    first_tool_ms: Optional[int],
    elapsed_ms_fn: Callable[[], int],
    emit_turn_event_fn: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    result = _event_result(message_id, first_tool_ms)
    index = pure_helpers.stream_int_value(pure_helpers.stream_value(event, "index"))
    if index is None:
        return result
    block = pure_helpers.stream_content_block(event)
    state = _content_block_state(index, block)
    block_type = pure_helpers.stream_string(state.get("type"))
    if not block_type:
        return result
    open_blocks[index] = state
    if block_type == "text" and state["text"]:
        emit_turn_event_fn(
            projection_helpers.stream_agent_message_event(
                event_type="item.updated",
                item_id=pure_helpers.stream_message_item_id(message_id, index),
                text=state["text"],
            )
        )
        return result
    if block_type in {"thinking", "reasoning"} and state["text"]:
        emit_turn_event_fn(
            projection_helpers.stream_reasoning_event(
                event_type="item.updated",
                item_id=pure_helpers.stream_message_item_id(message_id, index),
                text=state["text"],
            )
        )
        return result
    if block_type == "tool_use" and state["name"]:
        if result["first_tool_ms"] is None:
            result["first_tool_ms"] = elapsed_ms_fn()
        emit_turn_event_fn(
            projection_helpers.stream_function_call_started_event(
                call_id=state["id"],
                name=state["name"],
            )
        )
    return result


def _handle_content_block_delta(
    event: Any,
    *,
    message_id: str,
    open_blocks: Dict[int, Dict[str, Any]],
    first_tool_ms: Optional[int],
    emit_turn_event_fn: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    result = _event_result(message_id, first_tool_ms)
    index = pure_helpers.stream_int_value(pure_helpers.stream_value(event, "index"))
    if index is None or index not in open_blocks:
        return result
    state = open_blocks[index]
    delta = pure_helpers.stream_delta_payload(event)
    block_type = state.get("type")
    if block_type == "text":
        text_delta = str(delta.get("text") or "")
        if not text_delta:
            return result
        state["text"] = str(state.get("text") or "") + text_delta
        emit_turn_event_fn(
            projection_helpers.stream_agent_message_event(
                event_type="item.updated",
                item_id=pure_helpers.stream_message_item_id(message_id, index),
                text=str(state["text"]),
            )
        )
        return result
    if block_type in {"thinking", "reasoning"}:
        text_delta = str(delta.get("text") or "")
        if not text_delta:
            return result
        state["text"] = str(state.get("text") or "") + text_delta
        emit_turn_event_fn(
            projection_helpers.stream_reasoning_event(
                event_type="item.updated",
                item_id=pure_helpers.stream_message_item_id(message_id, index),
                text=str(state["text"]),
            )
        )
        return result
    if block_type == "tool_use":
        partial_json = delta.get("partial_json")
        if partial_json is None:
            partial_json = delta.get("text", delta.get("json"))
        if partial_json is not None:
            state["input_buffer"] = str(state.get("input_buffer") or "") + str(partial_json)
    return result


def _handle_content_block_stop(
    event: Any,
    *,
    allow_tools: bool,
    message_id: str,
    open_blocks: Dict[int, Dict[str, Any]],
    response_content: List[Any],
    first_tool_ms: Optional[int],
    emit_turn_event_fn: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    result = _event_result(message_id, first_tool_ms)
    index = pure_helpers.stream_int_value(pure_helpers.stream_value(event, "index"))
    if index is None:
        return result
    state = open_blocks.pop(index, None)
    if not isinstance(state, dict):
        return result
    block_type = pure_helpers.stream_string(state.get("type"))
    if block_type == "text":
        text = str(state.get("text") or "").strip()
        if not text:
            return result
        result["streamed_message_count_delta"] = 1
        response_content.append({"type": "text", "text": text})
        emit_turn_event_fn(
            projection_helpers.stream_agent_message_event(
                event_type="item.completed",
                item_id=pure_helpers.stream_message_item_id(message_id, index),
                text=text,
            )
        )
        return result
    if block_type in {"thinking", "reasoning"}:
        text = str(state.get("text") or "").strip()
        if text:
            emit_turn_event_fn(
                projection_helpers.stream_reasoning_event(
                    event_type="item.completed",
                    item_id=pure_helpers.stream_message_item_id(message_id, index),
                    text=text,
                )
            )
        return result
    if block_type == "tool_use":
        arguments = pure_helpers.stream_parse_tool_input(state)
        if arguments is None:
            return result
        call_id = pure_helpers.stream_string(state.get("id"))
        name = pure_helpers.stream_string(state.get("name"))
        response_content.append(
            {
                "type": "tool_use",
                "id": call_id,
                "name": name,
                "input": arguments,
            }
        )
        if name:
            emit_turn_event_fn(
                projection_helpers.stream_function_call_completed_event(
                    call_id=call_id,
                    name=name,
                    arguments=arguments,
                )
            )
        if allow_tools and name and call_id:
            result["early_response"] = SimpleNamespace(
                id=message_id,
                content=list(response_content),
            )
            result["should_break"] = True
        return result
    block = {"type": block_type}
    for key, value in state.items():
        if key in {"type", "index"}:
            continue
        if value not in (None, "", {}):
            block[key] = value
    response_content.append(block)
    return result


def _handle_message_stop(event: Any, *, message_id: str, first_tool_ms: Optional[int]) -> Dict[str, Any]:
    result = _event_result(message_id, first_tool_ms)
    response = pure_helpers.stream_dict_payload(pure_helpers.stream_value(event, "message"))
    if response:
        result["early_response"] = SimpleNamespace(**response)
    result["should_break"] = True
    return result


def handle_stream_event(
    *,
    event: Any,
    allow_tools: bool,
    message_id: str,
    open_blocks: Dict[int, Dict[str, Any]],
    response_content: List[Any],
    first_tool_ms: Optional[int],
    elapsed_ms_fn: Callable[[], int],
    emit_turn_event_fn: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    event_type = pure_helpers.stream_event_type(event)
    if event_type == "message_start":
        return _handle_message_start(event, message_id=message_id, first_tool_ms=first_tool_ms)
    if event_type == "content_block_start":
        return _handle_content_block_start(
            event,
            message_id=message_id,
            open_blocks=open_blocks,
            first_tool_ms=first_tool_ms,
            elapsed_ms_fn=elapsed_ms_fn,
            emit_turn_event_fn=emit_turn_event_fn,
        )
    if event_type == "content_block_delta":
        return _handle_content_block_delta(
            event,
            message_id=message_id,
            open_blocks=open_blocks,
            first_tool_ms=first_tool_ms,
            emit_turn_event_fn=emit_turn_event_fn,
        )
    if event_type == "content_block_stop":
        return _handle_content_block_stop(
            event,
            allow_tools=allow_tools,
            message_id=message_id,
            open_blocks=open_blocks,
            response_content=response_content,
            first_tool_ms=first_tool_ms,
            emit_turn_event_fn=emit_turn_event_fn,
        )
    if event_type == "message_stop":
        return _handle_message_stop(event, message_id=message_id, first_tool_ms=first_tool_ms)
    if event_type in {"message_delta", "ping"}:
        return _event_result(message_id, first_tool_ms)
    if event_type == "error":
        raise RuntimeError(
            pure_helpers.stream_string(pure_helpers.stream_value(event, "error")) or "anthropic_stream_error"
        )
    return _event_result(message_id, first_tool_ms)


__all__ = ["handle_stream_event"]
