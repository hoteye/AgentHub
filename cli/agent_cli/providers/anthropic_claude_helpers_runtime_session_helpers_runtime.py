from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.core.provider_session import ProviderSessionResult
from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.providers import anthropic_claude_streaming_runtime

StreamFallback = anthropic_claude_streaming_runtime.StreamFallback


def consume_streaming_request(
    *,
    request: dict[str, Any],
    stream_fn: Callable[..., Any],
    allow_tools: bool,
    turn_event_callback: Callable[[dict[str, Any]], None] | None,
) -> tuple[Any, list[Any], dict[str, Any]]:
    return anthropic_claude_streaming_runtime.consume_streaming_request(
        request=request,
        stream_fn=stream_fn,
        allow_tools=allow_tools,
        turn_event_callback=turn_event_callback,
    )


def send_session_request(
    *,
    input_items: list[dict[str, Any]],
    allow_tools: bool,
    messages: list[dict[str, Any]],
    create_fn: Callable[..., Any] | None,
    client: Any,
    model: str,
    system_prompt: str,
    max_tokens: int,
    default_max_tokens: int,
    supports_tools: bool,
    tool_specs: list[dict[str, Any]],
    response_count: int,
    prompt_cache_key: str | None,
    turn_event_callback: Callable[[dict[str, Any]], None] | None,
    stream_fn: Callable[..., Any] | None,
    tool_schema_fingerprint: str,
    tool_schema_cache_hit: bool,
    normalize_messages_fn: Callable[[list[dict[str, Any]]], tuple[list[str], list[dict[str, Any]]]],
    build_request_fn: Callable[..., dict[str, Any]],
    execute_request_fn: Callable[..., tuple[Any, list[Any]]],
    build_session_result_fn: Callable[..., Any],
    content_text_fn: Callable[[Any], str],
    tool_calls_fn: Callable[[Any], list[Any]],
    assistant_message_fn: Callable[[Any], dict[str, Any]],
    content_block_dict_fn: Callable[[Any], dict[str, Any]],
    log_request_fn: Callable[..., None],
    log_response_fn: Callable[..., None],
) -> tuple[ProviderSessionResult, dict[str, Any], int]:
    system_parts, normalized_input = normalize_messages_fn(input_items)
    if normalized_input:
        messages.extend(normalized_input)
    request = build_request_fn(
        model=model,
        base_system_prompt=system_prompt,
        system_parts=system_parts,
        messages=messages,
        max_tokens=int(max_tokens or default_max_tokens),
        supports_tools=supports_tools,
        allow_tools=allow_tools,
        tool_specs=tool_specs,
    )
    effective_prompt_cache_key = str(prompt_cache_key or "").strip() or None
    prompt_cache_skip_reason = ""
    if effective_prompt_cache_key:
        prompt_cache_skip_reason = "anthropic_messages_no_prompt_cache_api"

    response = None
    response_content: list[Any] = []
    extra_trace: dict[str, Any] = {
        "anthropic_streaming_enabled": False,
        "anthropic_streaming_fallback_reason": "",
        "anthropic_streaming_termination_reason": "",
        "time_to_first_event_ms": None,
        "time_to_first_tool_ms": None,
        "time_to_first_tool_call_ms": None,
        "streamed": False,
        "streamed_message_count": 0,
        "anthropic_prompt_cache_key_skipped_reason": prompt_cache_skip_reason,
        "anthropic_tool_schema_fingerprint": tool_schema_fingerprint,
        "anthropic_tool_schema_cache_hit": bool(tool_schema_cache_hit),
    }

    create = create_fn or client.messages.create
    should_stream = callable(stream_fn) and (allow_tools or turn_event_callback is not None)
    if should_stream:
        log_request_fn(request)
        try:
            response, response_content, streaming_trace = consume_streaming_request(
                request=request,
                stream_fn=stream_fn,
                allow_tools=allow_tools,
                turn_event_callback=turn_event_callback,
            )
            log_response_fn(response)
            extra_trace.update(dict(streaming_trace))
        except StreamFallback as exc:
            fallback_reason = str(exc.reason or "").strip() or "stream_request_failed"
            extra_trace["anthropic_streaming_fallback_reason"] = fallback_reason
            if timeline_debug_enabled():
                log_timeline(
                    "anthropic_messages.stream.fallback_to_create",
                    reason=fallback_reason,
                )
            response, response_content = execute_request_fn(
                request=request,
                create_fn=create,
                log_request_fn=lambda _: None,
                log_response_fn=log_response_fn,
            )
    else:
        if allow_tools or turn_event_callback is not None:
            extra_trace["anthropic_streaming_fallback_reason"] = "stream_api_unavailable"
        response, response_content = execute_request_fn(
            request=request,
            create_fn=create,
            log_request_fn=log_request_fn,
            log_response_fn=log_response_fn,
        )

    next_count = response_count + 1
    result, assistant_message = build_session_result_fn(
        response=response,
        response_content=response_content,
        response_count=next_count,
        content_text_fn=content_text_fn,
        tool_calls_fn=tool_calls_fn,
        assistant_message_fn=assistant_message_fn,
        content_block_dict_fn=content_block_dict_fn,
        extra_trace=extra_trace,
    )
    return result, assistant_message, next_count


__all__ = [
    "StreamFallback",
    "consume_streaming_request",
    "send_session_request",
]
