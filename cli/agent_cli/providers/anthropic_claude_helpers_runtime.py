from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.core.provider_session import ProviderSessionResult
from cli.agent_cli.models import AgentIntent, PromptAttachment
from cli.agent_cli.providers import (
    anthropic_claude_helpers_runtime_planner_helpers_runtime as anthropic_claude_helpers_runtime_planner_helpers_runtime_service,
)
from cli.agent_cli.providers import (
    anthropic_claude_helpers_runtime_pure_helpers_runtime as anthropic_claude_helpers_runtime_pure_helpers_runtime_service,
)
from cli.agent_cli.providers import (
    anthropic_claude_helpers_runtime_session_helpers_runtime as anthropic_claude_helpers_runtime_session_helpers_runtime_service,
)
from cli.agent_cli.providers import anthropic_claude_streaming_runtime


StreamFallback = anthropic_claude_streaming_runtime.StreamFallback
_stream_value = anthropic_claude_streaming_runtime.stream_value
_stream_dict_payload = anthropic_claude_streaming_runtime.stream_dict_payload
_stream_string = anthropic_claude_streaming_runtime.stream_string
_stream_event_type = anthropic_claude_streaming_runtime.stream_event_type
_stream_iterable = anthropic_claude_streaming_runtime.stream_iterable
_stream_final_response = anthropic_claude_streaming_runtime.stream_final_response
_stream_content_block = anthropic_claude_streaming_runtime.stream_content_block
_stream_delta_payload = anthropic_claude_streaming_runtime.stream_delta_payload
_stream_int_value = anthropic_claude_streaming_runtime.stream_int_value
_stream_message_item_id = anthropic_claude_streaming_runtime.stream_message_item_id
_stream_agent_message_event = anthropic_claude_streaming_runtime.stream_agent_message_event
_stream_reasoning_event = anthropic_claude_streaming_runtime.stream_reasoning_event
_stream_function_call_started_event = anthropic_claude_streaming_runtime.stream_function_call_started_event
_stream_function_call_completed_event = anthropic_claude_streaming_runtime.stream_function_call_completed_event
_stream_parse_tool_input = anthropic_claude_streaming_runtime.stream_parse_tool_input
_recover_partial_stream_content = anthropic_claude_streaming_runtime.recover_partial_stream_content


def consume_streaming_request(
    *,
    request: Dict[str, Any],
    stream_fn: Callable[..., Any],
    allow_tools: bool,
    turn_event_callback: Optional[Callable[[Dict[str, Any]], None]],
) -> Tuple[Any, List[Any], Dict[str, Any]]:
    return anthropic_claude_helpers_runtime_session_helpers_runtime_service.consume_streaming_request(
        request=request,
        stream_fn=stream_fn,
        allow_tools=allow_tools,
        turn_event_callback=turn_event_callback,
    )


def stable_tool_specs_payload(tool_specs: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], str]:
    return anthropic_claude_helpers_runtime_pure_helpers_runtime_service.stable_tool_specs_payload(
        tool_specs
    )


def send_session_request(
    *,
    input_items: List[Dict[str, Any]],
    allow_tools: bool,
    messages: List[Dict[str, Any]],
    create_fn: Optional[Callable[..., Any]],
    client: Any,
    model: str,
    system_prompt: str,
    max_tokens: int,
    default_max_tokens: int,
    supports_tools: bool,
    tool_specs: List[Dict[str, Any]],
    response_count: int,
    prompt_cache_key: Optional[str],
    turn_event_callback: Optional[Callable[[Dict[str, Any]], None]],
    stream_fn: Optional[Callable[..., Any]],
    tool_schema_fingerprint: str,
    tool_schema_cache_hit: bool,
    normalize_messages_fn: Callable[[List[Dict[str, Any]]], Tuple[List[str], List[Dict[str, Any]]]],
    build_request_fn: Callable[..., Dict[str, Any]],
    execute_request_fn: Callable[..., Tuple[Any, List[Any]]],
    build_session_result_fn: Callable[..., Any],
    content_text_fn: Callable[[Any], str],
    tool_calls_fn: Callable[[Any], List[Any]],
    assistant_message_fn: Callable[[Any], Dict[str, Any]],
    content_block_dict_fn: Callable[[Any], Dict[str, Any]],
    log_request_fn: Callable[..., None],
    log_response_fn: Callable[..., None],
) -> tuple[ProviderSessionResult, Dict[str, Any], int]:
    return anthropic_claude_helpers_runtime_session_helpers_runtime_service.send_session_request(
        input_items=input_items,
        allow_tools=allow_tools,
        messages=messages,
        create_fn=create_fn,
        client=client,
        model=model,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        default_max_tokens=default_max_tokens,
        supports_tools=supports_tools,
        tool_specs=tool_specs,
        response_count=response_count,
        prompt_cache_key=prompt_cache_key,
        turn_event_callback=turn_event_callback,
        stream_fn=stream_fn,
        tool_schema_fingerprint=tool_schema_fingerprint,
        tool_schema_cache_hit=tool_schema_cache_hit,
        normalize_messages_fn=normalize_messages_fn,
        build_request_fn=build_request_fn,
        execute_request_fn=execute_request_fn,
        build_session_result_fn=build_session_result_fn,
        content_text_fn=content_text_fn,
        tool_calls_fn=tool_calls_fn,
        assistant_message_fn=assistant_message_fn,
        content_block_dict_fn=content_block_dict_fn,
        log_request_fn=log_request_fn,
        log_response_fn=log_response_fn,
    )


def plan_without_tools(
    *,
    user_text: str,
    history: List[Dict[str, str]],
    attachments: Optional[List[PromptAttachment]],
    input_items: Optional[List[Dict[str, Any]]],
    build_session_fn: Callable[[], Any],
    conversation_input_items_fn: Callable[..., List[Dict[str, Any]]],
    history_for_conversation_fn: Callable[..., List[Dict[str, str]]],
    response_items_to_text_fn: Callable[[List[Dict[str, Any]]], str],
    default_response_items_fn: Callable[..., List[Dict[str, Any]]],
    agent_intent_factory: Callable[..., AgentIntent],
) -> AgentIntent:
    return anthropic_claude_helpers_runtime_planner_helpers_runtime_service.plan_without_tools(
        user_text=user_text,
        history=history,
        attachments=attachments,
        input_items=input_items,
        build_session_fn=build_session_fn,
        conversation_input_items_fn=conversation_input_items_fn,
        history_for_conversation_fn=history_for_conversation_fn,
        response_items_to_text_fn=response_items_to_text_fn,
        default_response_items_fn=default_response_items_fn,
        agent_intent_factory=agent_intent_factory,
    )


def history_for_conversation(
    history: List[Dict[str, str]],
    *,
    input_items: Optional[List[Dict[str, Any]]],
    input_items_have_assistant_turn_fn: Callable[[Optional[List[Dict[str, Any]]]], bool],
) -> List[Dict[str, str]]:
    return anthropic_claude_helpers_runtime_pure_helpers_runtime_service.history_for_conversation(
        history,
        input_items=input_items,
        input_items_have_assistant_turn_fn=input_items_have_assistant_turn_fn,
    )


def command_builder(
    *,
    host_platform: Any,
    plugin_manager_factory: Any,
    command_for_tool_call_fn: Callable[..., Optional[str]],
) -> Callable[[str, Dict[str, Any]], Optional[str]]:
    return anthropic_claude_helpers_runtime_pure_helpers_runtime_service.command_builder(
        host_platform=host_platform,
        plugin_manager_factory=plugin_manager_factory,
        command_for_tool_call_fn=command_for_tool_call_fn,
    )
