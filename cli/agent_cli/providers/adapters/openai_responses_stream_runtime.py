from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.core.provider_session import ProviderSessionResult
from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.models import response_item_text
from cli.agent_cli.providers.adapters import (
    openai_responses_stream_event_runtime,
    openai_responses_stream_recovery_runtime,
)
from cli.agent_cli.providers.adapters.openai_responses_output import (
    _json_ready,
    _summarize_response_output,
    extract_responses_followup_items,
    extract_responses_output_items,
)
from cli.agent_cli.providers.adapters.openai_responses_result_runtime import (
    has_provider_tool_response_items,
    provider_native_continuation_trace,
)
from cli.agent_cli.providers.adapters.openai_responses_stream_turn_events_runtime import (
    is_terminal_stream_response as _is_terminal_stream_response,
)
from cli.agent_cli.providers.adapters.openai_responses_stream_turn_events_runtime import (
    native_web_search_started_event as _native_web_search_started_event,
)
from cli.agent_cli.providers.adapters.openai_responses_stream_turn_events_runtime import (
    response_item_turn_event,
)
from cli.agent_cli.providers.token_usage_runtime import usage_from_provider_response

_STREAM_CLOSED_BEFORE_COMPLETED = "stream closed before response.completed"
_PARTIAL_TOOL_CALL_ITEM_TYPES = (
    openai_responses_stream_recovery_runtime._PARTIAL_TOOL_CALL_ITEM_TYPES
)
_followup_item_signature = openai_responses_stream_recovery_runtime.followup_item_signature


_native_web_search_state_key = openai_responses_stream_recovery_runtime.native_web_search_state_key
_remember_native_web_search_item_id = (
    openai_responses_stream_recovery_runtime.remember_native_web_search_item_id
)
_remember_native_web_search_pending_item = (
    openai_responses_stream_recovery_runtime.remember_native_web_search_pending_item
)
_drop_pending_native_web_search_item = (
    openai_responses_stream_recovery_runtime.drop_pending_native_web_search_item
)
_hydrate_native_web_search_done_item_id = (
    openai_responses_stream_recovery_runtime.hydrate_native_web_search_done_item_id
)
_recover_pending_native_web_search_items = (
    openai_responses_stream_recovery_runtime.recover_pending_native_web_search_items
)
_recover_pending_tool_call_items = (
    openai_responses_stream_recovery_runtime.recover_pending_tool_call_items
)
_recover_pending_message_items = (
    openai_responses_stream_recovery_runtime.recover_pending_message_items
)


def consume_stream(
    session: Any,
    stream: Any,
    *,
    turn_event_callback: Callable[[dict[str, Any]], None],
    initial_input_items: list[dict[str, Any]] | None = None,
) -> ProviderSessionResult:
    interrupt_requested = getattr(session, "_is_interrupt_requested", None)

    def _interrupted() -> bool:
        if not callable(interrupt_requested):
            return False
        try:
            return bool(interrupt_requested())
        except Exception:
            return False

    response = None
    stream_completed = False
    get_final_response = getattr(stream, "get_final_response", None)
    state: dict[str, Any] = {
        "response_items": [],
        "tool_calls": [],
        "followup_items": [],
        "output_text_parts": [],
        "message_buffers": {},
        "message_item_ids": {},
        "message_provider_item_ids": {},
        "message_item_phases": {},
        "emitted_message_ids": set(),
        "last_emitted_message_texts": {},
        "reasoning_buffers": {},
        "reasoning_item_ids": {},
        "emitted_reasoning_ids": set(),
        "emitted_reasoning_texts": set(),
        "last_emitted_reasoning_texts": {},
        "next_message_index": 0,
        "native_web_search_item_ids": {},
        "pending_native_web_search_items": {},
        "pending_tool_call_items": {},
        "pending_tool_call_keys_by_output_index": {},
        "pending_tool_call_keys_by_provider_id": {},
        "pending_function_call_arguments": {},
        "pending_custom_tool_call_inputs": {},
        "pending_tool_call_ready_keys": set(),
    }
    try:
        for event in stream:
            mark_stream_activity = getattr(session, "mark_active_stream_activity", None)
            if callable(mark_stream_activity):
                mark_stream_activity()
            event_type = str(getattr(event, "type", "") or "").strip()
            if timeline_debug_enabled():
                log_timeline("responses.stream.event", event_type=event_type)
            if event_type == "response.output_item.added":
                native_started_event = _native_web_search_started_event(event)
                if native_started_event is not None:
                    native_item = native_started_event.get("item")
                    if isinstance(native_item, dict):
                        _remember_native_web_search_item_id(
                            state,
                            event=event,
                            item_id=str(native_item.get("id") or "").strip(),
                        )
                        _remember_native_web_search_pending_item(
                            state,
                            event=event,
                        )
                    turn_event_callback(native_started_event)
                openai_responses_stream_event_runtime.response_output_item_added(
                    event,
                    state=state,
                    timeline_debug_enabled_fn=timeline_debug_enabled,
                    log_timeline_fn=log_timeline,
                )
                continue
            if event_type in {"response.output_text.delta", "response.refusal.delta"}:
                openai_responses_stream_event_runtime.response_output_text_event(
                    event,
                    state=state,
                    turn_event_callback=turn_event_callback,
                )
                continue
            if event_type in {"response.output_text.done", "response.refusal.done"}:
                openai_responses_stream_event_runtime.response_output_text_done(
                    event,
                    state=state,
                    turn_event_callback=turn_event_callback,
                )
                continue
            if event_type == "response.function_call_arguments.delta":
                openai_responses_stream_event_runtime.response_function_call_arguments_delta(
                    event,
                    state=state,
                )
                continue
            if event_type == "response.function_call_arguments.done":
                openai_responses_stream_event_runtime.response_function_call_arguments_done(
                    event,
                    state=state,
                )
                continue
            if event_type == "response.custom_tool_call_input.delta":
                openai_responses_stream_event_runtime.response_custom_tool_call_input_delta(
                    event,
                    state=state,
                )
                continue
            if event_type == "response.custom_tool_call_input.done":
                openai_responses_stream_event_runtime.response_custom_tool_call_input_done(
                    event,
                    state=state,
                )
                continue
            if event_type == "response.reasoning_summary_text.delta":
                openai_responses_stream_event_runtime.response_reasoning_summary_delta(
                    event,
                    state=state,
                    turn_event_callback=turn_event_callback,
                )
                continue
            if event_type == "response.reasoning_summary_text.done":
                openai_responses_stream_event_runtime.response_reasoning_summary_done(
                    event,
                    state=state,
                    turn_event_callback=turn_event_callback,
                )
                continue
            if event_type in {"response.reasoning_text.delta", "response.reasoning_text.done"}:
                continue
            if event_type == "response.output_item.done":
                _hydrate_native_web_search_done_item_id(state, event=event)
                _drop_pending_native_web_search_item(state, event=event)
                openai_responses_stream_event_runtime.response_output_item_done(
                    event,
                    state=state,
                    response_item_turn_event_fn=lambda item, item_id: response_item_turn_event(
                        item, item_id=item_id
                    ),
                    turn_event_callback=turn_event_callback,
                    timeline_debug_enabled_fn=timeline_debug_enabled,
                    log_timeline_fn=log_timeline,
                )
                continue
            if event_type in {"response.completed", "response.incomplete", "response.failed"}:
                completed_response = openai_responses_stream_event_runtime.response_completed(
                    event=event,
                    state=state,
                    turn_event_callback=turn_event_callback,
                    timeline_debug_enabled_fn=timeline_debug_enabled,
                    log_timeline_fn=log_timeline,
                    summarize_response_output_fn=_summarize_response_output,
                    json_ready_fn=_json_ready,
                )
                if completed_response is not None:
                    response = completed_response
                    stream_completed = True
    except Exception:
        if not _interrupted():
            raise

    if callable(get_final_response):
        try:
            response = get_final_response()
        except Exception:
            if not _interrupted():
                pass

    if not stream_completed and not _interrupted() and _is_terminal_stream_response(response):
        stream_completed = True

    if not stream_completed and not _interrupted():
        if timeline_debug_enabled():
            log_timeline(
                "responses.send.streaming.incomplete",
                error=_STREAM_CLOSED_BEFORE_COMPLETED,
                response_id=str(getattr(response, "id", "") or "").strip() or None,
                response_item_count=len(state["response_items"]),
                output_text_preview="".join(state["output_text_parts"]).strip()[:160],
            )
        raise RuntimeError(_STREAM_CLOSED_BEFORE_COMPLETED)

    response_id = str(getattr(response, "id", "") or "").strip()
    response_items = list(state["response_items"])
    tool_calls = list(state["tool_calls"])
    followup_items = list(state["followup_items"])
    output_text = "".join(state["output_text_parts"]).strip()
    response_status = str(getattr(response, "status", "") or "").strip().lower()
    if response is None or response_status in {"incomplete", "interrupted", "failed"}:
        _recover_pending_message_items(
            state=state,
            response_items=response_items,
            followup_items=followup_items,
        )
        _recover_pending_native_web_search_items(
            state=state,
            response_items=response_items,
            followup_items=followup_items,
        )
    _recover_pending_tool_call_items(
        state=state,
        response_items=response_items,
        tool_calls=tool_calls,
        followup_items=followup_items,
    )
    if response is not None:
        final_items = extract_responses_output_items(response)
        if final_items:
            response_items = final_items
        final_output_text = session._response_output_text(response)
        if final_output_text:
            output_text = final_output_text
        final_tool_calls = session._response_function_calls(response)
        if final_tool_calls:
            tool_calls = final_tool_calls
        final_followup_items = extract_responses_followup_items(response)
        if final_followup_items:
            followup_items = final_followup_items
        if response_status in {"incomplete", "interrupted", "failed"}:
            _recover_pending_tool_call_items(
                state=state,
                response_items=response_items,
                tool_calls=tool_calls,
                followup_items=followup_items,
            )
    if not output_text and response_items:
        partial_output_segments = []
        for item in list(response_items):
            item_type = str(getattr(item, "item_type", "") or "").strip().lower()
            role = str(getattr(item, "role", "") or "").strip().lower()
            if item_type != "message" and role != "assistant":
                continue
            text = response_item_text(item).strip()
            if text:
                partial_output_segments.append(text)
        if partial_output_segments:
            output_text = "\n".join(partial_output_segments).strip()
    if timeline_debug_enabled():
        log_timeline(
            "responses.send.streaming.end",
            response_id=response_id or None,
            tool_call_count=len(tool_calls),
            response_item_count=len(response_items),
            output_items=_summarize_response_output(response) if response is not None else [],
            output_text_preview=output_text[:160],
        )
        log_timeline(
            "responses.send.streaming.end_raw",
            response=_json_ready(response),
            followup_items=_json_ready(followup_items),
        )
    native_trace = provider_native_continuation_trace(
        response=response,
        response_items=response_items,
        output_text=output_text,
    )
    usage = usage_from_provider_response(response)
    answered = bool(
        not tool_calls
        and not has_provider_tool_response_items(response_items)
        and not native_trace["provider_native_continuation_pending"]
        and (output_text or response_items)
    )

    return ProviderSessionResult(
        output_text=output_text,
        tool_calls=tool_calls,
        response_items=response_items,
        continuation_input_items=[*list(initial_input_items or []), *followup_items],
        raw_response=response,
        response_id=response_id or None,
        trace={
            "tool_calls": [call.name for call in tool_calls],
            "tool_call_count": len(tool_calls),
            "answered": answered,
            "answer_preview": output_text[:120] if answered and output_text else "",
            "streamed": True,
            "streamed_message_count": len(state["emitted_message_ids"]),
            **({"usage": usage} if usage else {}),
            **native_trace,
        },
    )
