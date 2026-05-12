from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.models import ResponseInputItem
from cli.agent_cli.providers.adapters import (
    openai_responses_stream_event_normalization_helpers_runtime as _normalization_helpers,
)
from cli.agent_cli.providers.adapters import (
    openai_responses_stream_event_projection_helpers_runtime as _projection_helpers,
)
from cli.agent_cli.providers.adapters import (
    openai_responses_stream_event_pure_helpers_runtime as _pure_helpers,
)

_PARTIAL_TOOL_CALL_ITEM_TYPES = _pure_helpers.PARTIAL_TOOL_CALL_ITEM_TYPES
_pending_tool_call_key = _pure_helpers.pending_tool_call_key
_resolve_pending_tool_call_key = _normalization_helpers.resolve_pending_tool_call_key
_remember_pending_tool_call_item = _normalization_helpers.remember_pending_tool_call_item
_drop_pending_tool_call_item = _normalization_helpers.drop_pending_tool_call_item
_emit_completed_turn_event = _projection_helpers.emit_completed_turn_event


def response_function_call_arguments_delta(event: Any, *, state: dict[str, Any]) -> bool:
    return _normalization_helpers.response_function_call_arguments_delta(
        event,
        state=state,
    )


def response_function_call_arguments_done(event: Any, *, state: dict[str, Any]) -> bool:
    return _normalization_helpers.response_function_call_arguments_done(
        event,
        state=state,
    )


def response_custom_tool_call_input_delta(event: Any, *, state: dict[str, Any]) -> bool:
    return _normalization_helpers.response_custom_tool_call_input_delta(
        event,
        state=state,
    )


def response_custom_tool_call_input_done(event: Any, *, state: dict[str, Any]) -> bool:
    return _normalization_helpers.response_custom_tool_call_input_done(
        event,
        state=state,
    )


def response_output_item_added(
    event: Any,
    *,
    state: dict[str, Any],
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
) -> bool:
    return _normalization_helpers.response_output_item_added(
        event,
        state=state,
        timeline_debug_enabled_fn=timeline_debug_enabled_fn,
        log_timeline_fn=log_timeline_fn,
    )


def response_output_text_event(
    event: Any,
    *,
    state: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
) -> bool:
    return _normalization_helpers.response_output_text_event(
        event,
        state=state,
        turn_event_callback=turn_event_callback,
    )


def response_output_text_done(
    event: Any,
    *,
    state: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
) -> bool:
    return _normalization_helpers.response_output_text_done(
        event,
        state=state,
        turn_event_callback=turn_event_callback,
    )


def response_reasoning_summary_delta(
    event: Any,
    *,
    state: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
) -> bool:
    return _normalization_helpers.response_reasoning_summary_delta(
        event,
        state=state,
        turn_event_callback=turn_event_callback,
    )


def response_reasoning_summary_done(
    event: Any,
    *,
    state: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
) -> bool:
    return _normalization_helpers.response_reasoning_summary_done(
        event,
        state=state,
        turn_event_callback=turn_event_callback,
    )


def response_output_item_done(
    event: Any,
    *,
    state: dict[str, Any],
    response_item_turn_event_fn: Callable[[ResponseInputItem, str], dict[str, Any] | None],
    turn_event_callback: Callable[[dict[str, Any]], None],
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
) -> bool:
    return _projection_helpers.response_output_item_done(
        event,
        state=state,
        response_item_turn_event_fn=response_item_turn_event_fn,
        turn_event_callback=turn_event_callback,
        timeline_debug_enabled_fn=timeline_debug_enabled_fn,
        log_timeline_fn=log_timeline_fn,
    )


def response_completed(
    *,
    event: Any,
    state: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
    summarize_response_output_fn: Callable[[Any], Any],
    json_ready_fn: Callable[[Any], Any],
) -> Any:
    return _projection_helpers.response_completed(
        event=event,
        state=state,
        turn_event_callback=turn_event_callback,
        timeline_debug_enabled_fn=timeline_debug_enabled_fn,
        log_timeline_fn=log_timeline_fn,
        summarize_response_output_fn=summarize_response_output_fn,
        json_ready_fn=json_ready_fn,
    )


def flush_pending_buffers(*, state: dict[str, Any], turn_event_callback: Callable[[dict[str, Any]], None]) -> None:
    _projection_helpers.flush_pending_buffers(
        state=state,
        turn_event_callback=turn_event_callback,
    )


def flush_reasoning_only(*, state: dict[str, Any], turn_event_callback: Callable[[dict[str, Any]], None]) -> None:
    _projection_helpers.flush_reasoning_only(
        state=state,
        turn_event_callback=turn_event_callback,
    )
