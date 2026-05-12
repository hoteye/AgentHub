from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.core.provider_session import ProviderSessionResult, ProviderToolCall, default_tool_result_items
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.providers import anthropic_claude_helpers_runtime as anthropic_claude_helpers_runtime_service
from cli.agent_cli.providers import anthropic_claude_helpers_session_runtime as anthropic_claude_helpers_session_runtime_service
from cli.agent_cli.providers import anthropic_claude_session_runtime as session_runtime


def tool_result_block(
    *,
    call_id: str,
    output: Any,
    success: Optional[bool],
) -> Dict[str, Any]:
    return anthropic_claude_helpers_session_runtime_service.tool_result_block(
        call_id=call_id,
        output=output,
        success=success,
    )


def normalize_messages(
    *,
    input_items: List[Dict[str, Any]],
    tool_result_block_fn: Callable[..., Dict[str, Any]],
    message_text_fn: Callable[[Any], str],
    workspace_reference_message_fn: Callable[[Dict[str, Any]], str],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    return session_runtime.normalize_messages(
        input_items,
        tool_result_block_fn=tool_result_block_fn,
        message_text_fn=message_text_fn,
        workspace_reference_message_fn=workspace_reference_message_fn,
    )


def content_text(
    *,
    content: Any,
    content_block_dict_fn: Callable[[Any], Dict[str, Any]],
) -> str:
    return session_runtime.content_text(content, content_block_dict_fn=content_block_dict_fn)


def assistant_message(
    *,
    content: Any,
    content_block_dict_fn: Callable[[Any], Dict[str, Any]],
) -> Dict[str, Any]:
    return session_runtime.assistant_message(content, content_block_dict_fn=content_block_dict_fn)


def tool_calls(
    *,
    content: Any,
    content_block_dict_fn: Callable[[Any], Dict[str, Any]],
) -> List[ProviderToolCall]:
    return session_runtime.tool_calls(content, content_block_dict_fn=content_block_dict_fn)


def request_tool_specs_payload(session: Any) -> tuple[List[Dict[str, Any]], str, bool]:
    prepared_tool_specs, fingerprint, cache_hit = (
        anthropic_claude_helpers_session_runtime_service.request_tool_specs_payload(
            tool_specs=session.tool_specs,
            cached_payload=session._cached_tool_specs_payload,
            cached_fingerprint=session._cached_tool_specs_fingerprint,
            stable_tool_specs_payload_fn=anthropic_claude_helpers_runtime_service.stable_tool_specs_payload,
        )
    )
    if not cache_hit:
        session._cached_tool_specs_payload = list(prepared_tool_specs)
        session._cached_tool_specs_fingerprint = fingerprint
        return list(prepared_tool_specs), fingerprint, False
    session._tool_specs_cache_hits += 1
    return prepared_tool_specs, fingerprint, True


def resolve_stream_fn(
    *,
    client: Any,
    stream_fn: Optional[Callable[..., Any]],
) -> Optional[Callable[..., Any]]:
    return anthropic_claude_helpers_session_runtime_service.resolve_stream_fn(
        client=client,
        stream_fn=stream_fn,
    )


def send(
    session: Any,
    *,
    input_items: List[Dict[str, Any]],
    allow_tools: bool,
    prompt_cache_key: Optional[str],
    turn_event_callback: Optional[Callable[[Dict[str, Any]], None]],
    default_max_tokens: int,
    normalize_messages_fn: Callable[[List[Dict[str, Any]]], Tuple[List[str], List[Dict[str, Any]]]],
    content_text_fn: Callable[[Any], str],
    tool_calls_fn: Callable[[Any], List[ProviderToolCall]],
    assistant_message_fn: Callable[[Any], Dict[str, Any]],
    content_block_dict_fn: Callable[[Any], Dict[str, Any]],
    log_request_fn: Callable[[Any], None],
    log_response_fn: Callable[[Any], None],
) -> ProviderSessionResult:
    request_tool_specs, tool_schema_fingerprint, tool_schema_cache_hit = request_tool_specs_payload(session)
    result, assistant_message_payload, session._response_count = (
        anthropic_claude_helpers_runtime_service.send_session_request(
            input_items=input_items,
            allow_tools=allow_tools,
            messages=session._messages,
            create_fn=session.create_fn,
            client=session.client,
            model=session.model,
            system_prompt=session.system_prompt,
            max_tokens=session.max_tokens,
            default_max_tokens=default_max_tokens,
            supports_tools=session.supports_tools,
            tool_specs=request_tool_specs,
            response_count=session._response_count,
            prompt_cache_key=prompt_cache_key,
            turn_event_callback=turn_event_callback,
            stream_fn=resolve_stream_fn(client=session.client, stream_fn=session.stream_fn),
            tool_schema_fingerprint=tool_schema_fingerprint,
            tool_schema_cache_hit=tool_schema_cache_hit,
            normalize_messages_fn=normalize_messages_fn,
            build_request_fn=session_runtime.build_request,
            execute_request_fn=session_runtime.execute_request,
            build_session_result_fn=session_runtime.build_session_result,
            content_text_fn=content_text_fn,
            tool_calls_fn=tool_calls_fn,
            assistant_message_fn=assistant_message_fn,
            content_block_dict_fn=content_block_dict_fn,
            log_request_fn=log_request_fn,
            log_response_fn=log_response_fn,
        )
    )
    session._messages.append(assistant_message_payload)
    return result


def build_tool_result_items(
    *,
    call_id: str,
    command_text: Optional[str],
    assistant_text: str,
    events: List[ToolEvent],
    tool_result_projection_policy: str,
    workspace_root: str | None,
    tool_output_thread_id: str | None,
) -> List[Dict[str, Any]]:
    return default_tool_result_items(
        call_id=call_id,
        command_text=command_text,
        assistant_text=assistant_text,
        events=events,
        tool_result_projection_policy=str(tool_result_projection_policy or "").strip(),
        workspace_root=str(workspace_root or "").strip() or None,
        tool_output_thread_id=str(tool_output_thread_id or "").strip() or None,
    )
