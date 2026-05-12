from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

from cli.agent_cli.core.provider_session import ProviderSessionResult
from cli.agent_cli.debug_timeline import (
    _preview_text,
    log_timeline,
    summarize_current_turn_driver_tail,
    summarize_input_items_tail,
    summarize_protocol_items_tail,
    timeline_debug_enabled,
)
from cli.agent_cli.providers.adapters.openai_responses_error_runtime import (
    _attach_openai_recovery_diagnostics,
    call_with_responses_503_diagnostics,
)
from cli.agent_cli.providers.adapters.openai_responses_output import (
    _json_ready,
    _summarize_response_output,
)
from cli.agent_cli.providers.adapters.openai_responses_payload_runtime import (
    build_send_request,
)
from cli.agent_cli.providers.adapters.openai_responses_request_runtime import (
    execute_non_streaming_request,
    execute_streaming_request,
)
from cli.agent_cli.providers.adapters.openai_responses_result_runtime import (
    build_response_result,
)
from cli.agent_cli.providers.adapters.openai_responses_stream_runtime import (
    consume_stream as consume_stream_helper,
)
from cli.agent_cli.providers.openai_client import (
    is_retryable_provider_error,
    provider_retry_base_delay_seconds,
    provider_retry_max_delay_seconds,
)
from cli.agent_cli.providers.openai_stream_retry_runtime import (
    openai_stream_max_retries,
)
from cli.agent_cli.providers.responses_503_diagnostics import attach_responses_503_risks


def send(
    session: Any,
    *,
    input_items: list[dict[str, Any]],
    allow_tools: bool = True,
    previous_response_id: str | None = None,
    prompt_cache_key: str | None = None,
    turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> ProviderSessionResult:
    normalized_input, kwargs, effective_prompt_cache_key = build_send_request(
        session,
        input_items=input_items,
        allow_tools=allow_tools,
        previous_response_id=previous_response_id,
        prompt_cache_key=prompt_cache_key,
        turn_event_callback=turn_event_callback,
    )
    if timeline_debug_enabled():
        request_payload = _json_ready(kwargs)
        request_body = dict(request_payload or {})
        transport_extra_headers = request_body.pop("extra_headers", None)
        function_call_outputs = [
            dict(item)
            for item in list(normalized_input or [])
            if isinstance(item, dict)
            and str(item.get("type") or "").strip()
            in {"function_call_output", "custom_tool_call_output"}
        ]
        log_timeline(
            "responses.send.request",
            model=session.model,
            transport_kind=str(getattr(session.client, "transport_kind", "") or "").strip() or None,
            base_url=_preview_text(getattr(session.client, "base_url", None), max_chars=200),
            allow_tools=allow_tools,
            previous_response_id=kwargs.get("previous_response_id"),
            input_count=len(list(normalized_input or [])),
            input_tail=summarize_input_items_tail(normalized_input, tail_len=8),
            tool_count=len(list(session.tool_specs or [])) if allow_tools else 0,
            tool_names=(
                [
                    str(item.get("name") or "").strip()
                    for item in list(session.tool_specs or [])
                    if isinstance(item, dict) and str(item.get("name") or "").strip()
                ]
                if allow_tools
                else []
            ),
            protocol_input_tail=summarize_protocol_items_tail(normalized_input, tail_len=8),
            current_turn_driver_tail=summarize_current_turn_driver_tail(
                normalized_input, tail_len=8
            ),
            parallel_tool_calls=bool(kwargs.get("parallel_tool_calls")),
            stream=bool(kwargs.get("stream")),
        )
        log_timeline(
            "responses.send.request_raw",
            request=request_body,
            provider_name=str(session.provider_name or "").strip() or None,
            base_url=str(
                session.base_url or getattr(session.client, "base_url", None) or ""
            ).strip()
            or None,
        )
        if transport_extra_headers:
            log_timeline(
                "responses.send.transport.request_raw",
                transport={"extra_headers": transport_extra_headers},
                provider_name=str(session.provider_name or "").strip() or None,
                base_url=str(
                    session.base_url or getattr(session.client, "base_url", None) or ""
                ).strip()
                or None,
            )
        if function_call_outputs:
            log_timeline(
                "responses.send.function_call_output_input_raw",
                items=_json_ready(function_call_outputs),
            )
    if turn_event_callback is not None:
        return send_streaming(session, kwargs, turn_event_callback=turn_event_callback)

    response = call_with_responses_503_diagnostics(
        lambda: execute_non_streaming_request(session, kwargs=kwargs),
        payload={"input": normalized_input},
        source="responses.send",
    )
    result = build_response_result(
        session,
        response=response,
        normalized_input=normalized_input,
    )
    tool_calls = result.tool_calls
    output_text = result.output_text
    response_items = result.response_items
    followup_items = result.continuation_input_items[len(normalized_input) :]
    if timeline_debug_enabled():
        log_timeline(
            "responses.send.response_summary",
            response_id=str(getattr(response, "id", "") or "").strip() or None,
            output_items=_summarize_response_output(response),
            tool_call_names=[call.name for call in tool_calls],
            output_text_preview=_preview_text(output_text, max_chars=200),
            protocol_input_tail=summarize_protocol_items_tail(normalized_input, tail_len=8),
            current_turn_driver_tail=summarize_current_turn_driver_tail(
                normalized_input, tail_len=8
            ),
            response_item_tail=summarize_protocol_items_tail(
                [item.to_dict() for item in list(response_items or [])],
                tail_len=8,
            ),
            next_turn_protocol_tail=summarize_protocol_items_tail(followup_items, tail_len=8),
        )
        log_timeline(
            "responses.send.response_raw",
            response=_json_ready(response),
        )
    return result


def send_streaming(
    session: Any,
    kwargs: dict[str, Any],
    *,
    turn_event_callback: Callable[[dict[str, Any]], None],
) -> ProviderSessionResult:
    source = "responses.send.streaming"
    payload = {"input": list(kwargs.get("input") or [])}
    max_retries = openai_stream_max_retries()
    base_delay = provider_retry_base_delay_seconds()
    max_delay = provider_retry_max_delay_seconds()
    last_error: Exception | None = None
    for retry_attempt in range(0, max_retries + 1):
        try:
            result = execute_streaming_request(
                session,
                kwargs=kwargs,
                turn_event_callback=turn_event_callback,
                consume_stream=consume_stream,
            )
            if retry_attempt > 0:
                trace = dict(getattr(result, "trace", {}) or {})
                trace["stream_retry_attempts"] = retry_attempt
                trace["stream_max_retries"] = max_retries
                result.trace = trace
            return result
        except Exception as exc:
            last_error = exc
            retryable = is_retryable_provider_error(exc)
            if retry_attempt >= max_retries or not retryable:
                attach_responses_503_risks(exc, payload, source=source)
                _attach_openai_recovery_diagnostics(exc, source=source)
                raise
            next_retry = retry_attempt + 1
            delay = min(max_delay, base_delay * (2**retry_attempt))
            delay += random.uniform(0.0, min(0.25, delay * 0.2))
            message = f"Reconnecting... {next_retry}/{max_retries}"
            if timeline_debug_enabled():
                log_timeline(
                    "responses.send.streaming.retry",
                    retry_attempt=next_retry,
                    max_retries=max_retries,
                    delay_seconds=round(delay, 3),
                    error_type=type(exc).__name__,
                    error_text=str(exc),
                )
            turn_event_callback(
                {
                    "type": "provider.retry",
                    "message": message,
                    "source": source,
                    "retry_attempt": next_retry,
                    "max_retries": max_retries,
                    "delay_seconds": round(delay, 3),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            time.sleep(delay)
    if last_error is not None:
        attach_responses_503_risks(last_error, payload, source=source)
        _attach_openai_recovery_diagnostics(last_error, source=source)
        raise last_error
    raise RuntimeError("stream retry loop exited without a result")


def consume_stream(
    session: Any,
    stream: Any,
    *,
    turn_event_callback: Callable[[dict[str, Any]], None],
    initial_input_items: list[dict[str, Any]] | None = None,
) -> ProviderSessionResult:
    return consume_stream_helper(
        session,
        stream,
        turn_event_callback=turn_event_callback,
        initial_input_items=initial_input_items,
    )
