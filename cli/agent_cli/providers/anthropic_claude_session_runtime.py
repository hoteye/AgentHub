from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.core.provider_session import ProviderSessionResult, ProviderToolCall
from cli.agent_cli.debug_timeline import json_ready, log_timeline, timeline_debug_enabled
from cli.agent_cli.providers import (
    anthropic_claude_session_runtime_normalization_helpers_runtime as normalization_helpers,
)
from cli.agent_cli.providers import (
    anthropic_claude_session_runtime_projection_helpers_runtime as projection_helpers,
)
from cli.agent_cli.providers import anthropic_claude_session_runtime_pure_helpers_runtime as pure_helpers
from cli.agent_cli.providers.error_diagnostics_runtime import (
    CONNECTION_ERROR_MARKERS,
    attach_provider_recovery_diagnostics,
    contains_any,
    normalized_error_text,
)
from cli.agent_cli.providers.openai_client import call_with_provider_retries, is_retryable_provider_error


def _anthropic_retryable_provider_error(exc: Exception) -> bool:
    try:
        from anthropic import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

        if isinstance(exc, (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)):
            return True
    except Exception:
        pass
    return is_retryable_provider_error(exc) or contains_any(normalized_error_text(exc), CONNECTION_ERROR_MARKERS)


def _attach_anthropic_recovery_diagnostics(
    exc: Exception,
    *,
    source: str,
) -> None:
    attach_provider_recovery_diagnostics(
        exc,
        provider_family="anthropic",
        source=source,
        retryable=_anthropic_retryable_provider_error(exc),
    )


def normalize_messages(
    input_items: List[Dict[str, Any]],
    *,
    tool_result_block_fn: Callable[..., Dict[str, Any]],
    message_text_fn: Callable[[Any], str],
    workspace_reference_message_fn: Callable[[Dict[str, Any]], str],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    return normalization_helpers.normalize_messages(
        input_items,
        tool_result_block_fn=tool_result_block_fn,
        message_text_fn=message_text_fn,
        workspace_reference_message_fn=workspace_reference_message_fn,
        timeline_debug_enabled_fn=timeline_debug_enabled,
        log_timeline_fn=log_timeline,
        json_ready_fn=json_ready,
    )


def content_text(content: Any, *, content_block_dict_fn: Callable[[Any], Dict[str, Any]]) -> str:
    return projection_helpers.content_text(content, content_block_dict_fn=content_block_dict_fn)


def server_tool_names(content: Any, *, content_block_dict_fn: Callable[[Any], Dict[str, Any]]) -> List[str]:
    return projection_helpers.server_tool_names(content, content_block_dict_fn=content_block_dict_fn)


def assistant_message(content: Any, *, content_block_dict_fn: Callable[[Any], Dict[str, Any]]) -> Dict[str, Any]:
    return projection_helpers.assistant_message(content, content_block_dict_fn=content_block_dict_fn)


def tool_calls(content: Any, *, content_block_dict_fn: Callable[[Any], Dict[str, Any]]) -> List[ProviderToolCall]:
    return projection_helpers.tool_calls(content, content_block_dict_fn=content_block_dict_fn)


def build_request(
    *,
    model: str,
    base_system_prompt: str,
    system_parts: List[str],
    messages: List[Dict[str, Any]],
    max_tokens: int,
    supports_tools: bool,
    allow_tools: bool,
    tool_specs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return pure_helpers.build_request(
        model=model,
        base_system_prompt=base_system_prompt,
        system_parts=system_parts,
        messages=messages,
        max_tokens=max_tokens,
        supports_tools=supports_tools,
        allow_tools=allow_tools,
        tool_specs=tool_specs,
    )


def execute_request(
    *,
    request: Dict[str, Any],
    create_fn: Callable[..., Any],
    log_request_fn: Callable[[Dict[str, Any]], None],
    log_response_fn: Callable[[Any], None],
) -> tuple[Any, List[Any]]:
    log_request_fn(request)
    try:
        response = call_with_provider_retries(lambda: create_fn(**request))
    except Exception as exc:
        _attach_anthropic_recovery_diagnostics(exc, source="anthropic.messages.create")
        raise
    log_response_fn(response)
    response_content = list(getattr(response, "content", []) or [])
    return response, response_content


def send_request(
    *,
    model: str,
    base_system_prompt: str,
    system_parts: List[str],
    messages: List[Dict[str, Any]],
    max_tokens: int,
    supports_tools: bool,
    allow_tools: bool,
    tool_specs: List[Dict[str, Any]],
    log_request_fn: Callable[[Dict[str, Any]], None],
    create_fn: Callable[..., Any],
    log_response_fn: Callable[[Any], None],
) -> tuple[Dict[str, Any], Any, List[Any]]:
    request = build_request(
        model=model,
        base_system_prompt=base_system_prompt,
        system_parts=system_parts,
        messages=messages,
        max_tokens=max_tokens,
        supports_tools=supports_tools,
        allow_tools=allow_tools,
        tool_specs=tool_specs,
    )
    response, response_content = execute_request(
        request=request,
        create_fn=create_fn,
        log_request_fn=log_request_fn,
        log_response_fn=log_response_fn,
    )
    return request, response, response_content


def build_session_result(
    *,
    response: Any,
    response_content: List[Any],
    response_count: int,
    content_text_fn: Callable[[Any], str],
    tool_calls_fn: Callable[[Any], List[ProviderToolCall]],
    assistant_message_fn: Callable[[Any], Dict[str, Any]],
    content_block_dict_fn: Callable[[Any], Dict[str, Any]],
    extra_trace: Optional[Dict[str, Any]] = None,
) -> tuple[ProviderSessionResult, Dict[str, Any]]:
    return projection_helpers.build_session_result(
        response=response,
        response_content=response_content,
        response_count=response_count,
        content_text_fn=content_text_fn,
        tool_calls_fn=tool_calls_fn,
        assistant_message_fn=assistant_message_fn,
        content_block_dict_fn=content_block_dict_fn,
        extra_trace=extra_trace,
    )
