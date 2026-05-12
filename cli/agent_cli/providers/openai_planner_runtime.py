from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.models import AgentIntent, PromptAttachment
from cli.agent_cli.providers import (
    openai_planner_runtime_helpers_runtime as runtime_helpers,
)
from cli.agent_cli.providers import (
    openai_planner_runtime_projection_helpers_runtime as projection_helpers,
)
from cli.agent_cli.providers import openai_planner_runtime_pure_helpers_runtime as pure_helpers
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession

_timing_int = pure_helpers.timing_int
_timing_list = pure_helpers.timing_list
_merge_native_tool_timings = pure_helpers.merge_native_tool_timings


def plan_with_native_tools(
    planner: Any,
    user_text: str,
    history: List[Dict[str, str]],
    *,
    tool_executor: Any,
    attachments: Optional[List[PromptAttachment]] = None,
    input_items: Optional[List[Dict[str, Any]]] = None,
    prompt_cache_key: Optional[str] = None,
    turn_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    provider_session_id: Optional[str] = None,
    provider_turn_id: Optional[str] = None,
    provider_sandbox_mode: Optional[str] = None,
    initial_previous_response_id: Optional[str] = None,
    responses_session_cls: Any = OpenAIResponsesSession,
    turn_engine_cls: Any = TurnEngine,
) -> AgentIntent:
    started_at = time.perf_counter()
    messages = runtime_helpers.conversation_messages(
        planner=planner,
        user_text=user_text,
        history=history,
        attachments=attachments,
        input_items=input_items,
    )
    session = runtime_helpers.create_native_tool_session(
        planner=planner,
        tool_executor=tool_executor,
        prompt_cache_key=prompt_cache_key,
        provider_session_id=provider_session_id,
        provider_turn_id=provider_turn_id,
        provider_sandbox_mode=provider_sandbox_mode,
        responses_session_cls=responses_session_cls,
    )
    terminal_handler = runtime_helpers.build_terminal_handler(
        planner=planner,
        attachments=attachments,
    )
    followup_handler = runtime_helpers.build_followup_handler(
        planner=planner,
        session=session,
        tool_executor=tool_executor,
        terminal_handler=terminal_handler,
        attachments=attachments,
        turn_event_callback=turn_event_callback,
    )
    raw_intent = runtime_helpers.run_turn_engine_with_active_session(
        planner=planner,
        session=session,
        user_text=user_text,
        initial_input=messages,
        initial_previous_response_id=initial_previous_response_id,
        tool_executor=tool_executor,
        turn_event_callback=turn_event_callback,
        followup_handler=followup_handler,
        terminal_handler=terminal_handler,
        prompt_cache_key=prompt_cache_key,
        turn_engine_cls=turn_engine_cls,
    )
    return projection_helpers.project_native_tool_loop_intent(
        raw_intent=raw_intent,
        user_text=user_text,
        attachments=attachments,
        total_elapsed_ms=int((time.perf_counter() - started_at) * 1000),
        tool_item_events_from_turn_events_fn=planner._tool_item_events_from_turn_events,
        synthetic_recovery_allowed=planner._synthetic_recovery_allowed(),
        synthesize_after_tool_loop_fn=planner._fresh_synthesis_after_tool_loop,
        canonical_turn_events_fn=planner._canonical_turn_events,
    )


def plan_native_without_tools(
    planner: Any,
    user_text: str,
    history: List[Dict[str, str]],
    *,
    attachments: Optional[List[PromptAttachment]] = None,
    input_items: Optional[List[Dict[str, Any]]] = None,
    prompt_cache_key: Optional[str] = None,
    turn_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    provider_session_id: Optional[str] = None,
    provider_turn_id: Optional[str] = None,
    provider_sandbox_mode: Optional[str] = None,
    responses_session_cls: Any = OpenAIResponsesSession,
) -> AgentIntent:
    started_at = time.perf_counter()
    messages = runtime_helpers.conversation_messages(
        planner=planner,
        user_text=user_text,
        history=history,
        attachments=attachments,
        input_items=input_items,
    )
    session = runtime_helpers.create_native_without_tools_session(
        planner=planner,
        prompt_cache_key=prompt_cache_key,
        provider_session_id=provider_session_id,
        provider_turn_id=provider_turn_id,
        provider_sandbox_mode=provider_sandbox_mode,
        responses_session_cls=responses_session_cls,
    )
    request_started_at = time.perf_counter()
    result = runtime_helpers.send_without_tools_with_active_session(
        planner=planner,
        session=session,
        input_items=messages,
        prompt_cache_key=prompt_cache_key,
        turn_event_callback=turn_event_callback,
    )
    initial_model_ms = int((time.perf_counter() - request_started_at) * 1000)
    return projection_helpers.project_native_without_tools_intent(
        result=result,
        initial_model_ms=initial_model_ms,
        total_elapsed_ms=int((time.perf_counter() - started_at) * 1000),
        compose_turn_events_fn=planner._compose_turn_events,
    )


def plan_without_native_tools(
    planner: Any,
    user_text: str,
    history: List[Dict[str, str]],
    *,
    attachments: Optional[List[PromptAttachment]] = None,
    input_items: Optional[List[Dict[str, Any]]] = None,
) -> AgentIntent:
    if planner.reference_parity_enabled:
        raise RuntimeError("_plan_without_native_tools is disabled when reference parity is enabled")
    started_at = time.perf_counter()
    messages = runtime_helpers.conversation_messages(
        planner=planner,
        user_text=user_text,
        history=history,
        attachments=attachments,
        input_items=input_items,
    )
    kwargs = pure_helpers.stream_text_request_kwargs(
        model=planner.config.model,
        instructions=planner.system_prompt,
        input_items=messages,
        reasoning=planner._reasoning_request(),
    )
    initial_started_at = time.perf_counter()
    raw_text = planner._collect_stream_text(**kwargs)
    initial_model_ms = int((time.perf_counter() - initial_started_at) * 1000)
    return projection_helpers.project_legacy_json_intent(
        intent=planner._intent_from_raw_text(raw_text),
        initial_model_ms=initial_model_ms,
        total_elapsed_ms=int((time.perf_counter() - started_at) * 1000),
    )
