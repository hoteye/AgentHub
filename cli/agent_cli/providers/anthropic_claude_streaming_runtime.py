from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any

from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.providers import (
    anthropic_claude_streaming_runtime_event_helpers_runtime as event_helpers,
)
from cli.agent_cli.providers import (
    anthropic_claude_streaming_runtime_normalization_helpers_runtime as normalization_helpers,
)
from cli.agent_cli.providers import (
    anthropic_claude_streaming_runtime_projection_helpers_runtime as projection_helpers,
)
from cli.agent_cli.providers import (
    anthropic_claude_streaming_runtime_pure_helpers_runtime as pure_helpers,
)

StreamFallback = pure_helpers.StreamFallback
stream_value = pure_helpers.stream_value
stream_dict_payload = pure_helpers.stream_dict_payload
stream_string = pure_helpers.stream_string
stream_event_type = pure_helpers.stream_event_type
stream_iterable = pure_helpers.stream_iterable
stream_final_response = pure_helpers.stream_final_response
stream_content_block = pure_helpers.stream_content_block
stream_delta_payload = pure_helpers.stream_delta_payload
stream_int_value = pure_helpers.stream_int_value
stream_message_item_id = pure_helpers.stream_message_item_id
stream_parse_tool_input = pure_helpers.stream_parse_tool_input
stream_agent_message_event = projection_helpers.stream_agent_message_event
stream_reasoning_event = projection_helpers.stream_reasoning_event
stream_function_call_started_event = projection_helpers.stream_function_call_started_event
stream_function_call_completed_event = projection_helpers.stream_function_call_completed_event
recover_partial_stream_content = normalization_helpers.recover_partial_stream_content


def _type_name(value: Any) -> str:
    return type(value).__name__


def _callable_label(value: Any) -> str:
    name = str(getattr(value, "__qualname__", "") or getattr(value, "__name__", "") or "").strip()
    owner = getattr(value, "__self__", None)
    if owner is not None:
        owner_type = type(owner).__name__
        return f"{owner_type}.{name or '<callable>'}"
    return name or _type_name(value)


def _stream_capabilities(value: Any) -> dict[str, Any]:
    return {
        "type": _type_name(value),
        "has_iter": hasattr(value, "__iter__"),
        "has_enter": callable(getattr(value, "__enter__", None)),
        "has_events": callable(getattr(value, "events", None)),
        "has_stream_attr": hasattr(value, "stream"),
        "has_get_final_message": callable(getattr(value, "get_final_message", None)),
        "has_get_final_response": callable(getattr(value, "get_final_response", None)),
    }


def _log_stream(stage: str, **payload: Any) -> None:
    if timeline_debug_enabled():
        log_timeline(stage, **payload)


def consume_streaming_request(
    *,
    request: dict[str, Any],
    stream_fn: Callable[..., Any],
    allow_tools: bool,
    turn_event_callback: Callable[[dict[str, Any]], None] | None,
) -> tuple[Any, list[Any], dict[str, Any]]:
    started_at = time.perf_counter()
    message_id = ""
    first_raw_event_ms: int | None = None
    first_event_ms: int | None = None
    first_tool_ms: int | None = None
    streamed_message_count = 0
    response_content: list[Any] = []
    open_blocks: dict[int, dict[str, Any]] = {}
    early_response: Any = None
    termination_reason = ""

    def _elapsed_ms() -> int:
        return int((time.perf_counter() - started_at) * 1000)

    def _mark_first_event() -> None:
        nonlocal first_event_ms
        if first_event_ms is None:
            first_event_ms = _elapsed_ms()

    def _emit_turn_event(payload: dict[str, Any]) -> None:
        _mark_first_event()
        if callable(turn_event_callback):
            turn_event_callback(dict(payload))

    _log_stream(
        "anthropic_messages.stream.request_start",
        stream_fn=_callable_label(stream_fn),
        model=str(request.get("model") or ""),
        message_count=(
            len(request.get("messages") or []) if isinstance(request.get("messages"), list) else 0
        ),
        tool_count=len(request.get("tools") or []) if isinstance(request.get("tools"), list) else 0,
    )
    try:
        stream_resource = stream_fn(**request)
    except Exception as exc:
        _log_stream(
            "anthropic_messages.stream.request_error",
            elapsed_ms=_elapsed_ms(),
            error_type=type(exc).__name__,
            error_text=str(exc),
        )
        raise StreamFallback(f"stream_request_failed:{type(exc).__name__}") from exc
    _log_stream(
        "anthropic_messages.stream.resource",
        elapsed_ms=_elapsed_ms(),
        **_stream_capabilities(stream_resource),
    )

    try:
        with ExitStack() as stack:
            stream_handle = stream_resource
            if callable(getattr(stream_resource, "__enter__", None)):
                stream_handle = stack.enter_context(stream_resource)
                _log_stream(
                    "anthropic_messages.stream.entered",
                    elapsed_ms=_elapsed_ms(),
                    **_stream_capabilities(stream_handle),
                )
            iterator = stream_iterable(stream_handle)
            _log_stream(
                "anthropic_messages.stream.iterator",
                elapsed_ms=_elapsed_ms(),
                iterator_type=_type_name(iterator),
                iterator_is_handle=iterator is stream_handle,
            )
            for event in iterator:
                if first_raw_event_ms is None:
                    first_raw_event_ms = _elapsed_ms()
                    _log_stream(
                        "anthropic_messages.stream.first_event",
                        elapsed_ms=first_raw_event_ms,
                        event_type=stream_event_type(event),
                        event_object_type=_type_name(event),
                    )
                event_result = event_helpers.handle_stream_event(
                    event=event,
                    allow_tools=allow_tools,
                    message_id=message_id,
                    open_blocks=open_blocks,
                    response_content=response_content,
                    first_tool_ms=first_tool_ms,
                    elapsed_ms_fn=_elapsed_ms,
                    emit_turn_event_fn=_emit_turn_event,
                )
                message_id = str(event_result.get("message_id") or message_id)
                first_tool_ms = event_result.get("first_tool_ms")
                streamed_message_count += int(event_result.get("streamed_message_count_delta") or 0)
                if event_result.get("early_response") is not None:
                    early_response = event_result.get("early_response")
                if event_result.get("should_break"):
                    break
            if early_response is None:
                final_response = stream_final_response(stream_handle)
                if final_response is not None:
                    early_response = final_response
    except StreamFallback:
        _log_stream(
            "anthropic_messages.stream.fallback",
            elapsed_ms=_elapsed_ms(),
            reason="stream_api_invalid",
        )
        raise
    except Exception as exc:
        streamed_message_count += recover_partial_stream_content(
            open_blocks=open_blocks,
            response_content=response_content,
            allow_tools=allow_tools,
            message_id=message_id,
            emit_turn_event_fn=_emit_turn_event,
        )
        open_blocks.clear()
        if first_event_ms is None and not response_content:
            _log_stream(
                "anthropic_messages.stream.fallback",
                elapsed_ms=_elapsed_ms(),
                reason=f"stream_request_failed:{type(exc).__name__}",
                error_type=type(exc).__name__,
                error_text=str(exc),
            )
            raise StreamFallback(f"stream_request_failed:{type(exc).__name__}") from exc
        termination_reason = f"stream_interrupted_partial_response:{type(exc).__name__}"
        _log_stream(
            "anthropic_messages.stream.interrupted",
            elapsed_ms=_elapsed_ms(),
            reason=termination_reason,
            recovered_content_count=len(response_content),
        )

    response = early_response
    if response is None:
        response = SimpleNamespace(id=message_id, content=list(response_content))
    final_content = list(getattr(response, "content", []) or [])
    if final_content:
        response_content = final_content
    return (
        response,
        response_content,
        {
            "anthropic_streaming_enabled": True,
            "anthropic_streaming_fallback_reason": "",
            "time_to_first_event_ms": first_event_ms,
            "time_to_first_tool_ms": first_tool_ms,
            "time_to_first_tool_call_ms": first_tool_ms,
            "streamed": True,
            "streamed_message_count": streamed_message_count,
            "anthropic_streaming_termination_reason": termination_reason,
        },
    )


__all__ = [
    "StreamFallback",
    "consume_streaming_request",
    "recover_partial_stream_content",
    "stream_agent_message_event",
    "stream_content_block",
    "stream_delta_payload",
    "stream_dict_payload",
    "stream_event_type",
    "stream_final_response",
    "stream_function_call_completed_event",
    "stream_function_call_started_event",
    "stream_int_value",
    "stream_iterable",
    "stream_message_item_id",
    "stream_parse_tool_input",
    "stream_reasoning_event",
    "stream_string",
    "stream_value",
]
