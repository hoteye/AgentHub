from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.providers.adapters import (
    openai_responses_adapter_runtime as openai_responses_adapter_runtime_service,
)


def build_send_request(
    session: Any,
    *,
    input_items: list[dict[str, Any]],
    allow_tools: bool,
    previous_response_id: str | None,
    prompt_cache_key: str | None,
    turn_event_callback: Callable[[dict[str, Any]], None] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    normalized_input = session._normalize_input_items(
        input_items, reference_parity=session.reference_parity
    )
    kwargs: dict[str, Any] = {
        "model": session.model,
        "instructions": session.instructions,
        "input": normalized_input,
        "store": False,
        "stream": bool(turn_event_callback),
    }
    if previous_response_id and session._uses_previous_response_id():
        kwargs["previous_response_id"] = previous_response_id
    effective_prompt_cache_key = openai_responses_adapter_runtime_service.resolve_conversation_id(
        prompt_cache_key=prompt_cache_key,
        session_prompt_cache_key=getattr(session, "prompt_cache_key", None),
        session_id=getattr(session, "session_id", None),
        include_session_id_fallback=bool(getattr(session, "reference_parity", False)),
    )
    if effective_prompt_cache_key:
        kwargs["prompt_cache_key"] = effective_prompt_cache_key
    reasoning = session._reasoning_request()
    if reasoning:
        kwargs["reasoning"] = reasoning
        kwargs["include"] = session._responses_include()
    text = session._text_request()
    if text:
        kwargs["text"] = text
    client_metadata = session._client_metadata_request()
    if client_metadata:
        kwargs["client_metadata"] = client_metadata
    extra_headers = session._request_extra_headers(
        prompt_cache_key=effective_prompt_cache_key,
        stream=bool(turn_event_callback),
    )
    if extra_headers:
        kwargs["extra_headers"] = extra_headers
    if allow_tools:
        kwargs.update(
            {
                "tools": session.tool_specs,
                "tool_choice": "auto",
                "parallel_tool_calls": bool(getattr(session, "reference_parity", False)),
            }
        )
    return normalized_input, kwargs, effective_prompt_cache_key
