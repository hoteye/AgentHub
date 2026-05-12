from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.models import AgentIntent, PromptAttachment, ToolEvent
from cli.agent_cli.providers import (
    openai_planner_runtime_projection_helpers_runtime as projection_helpers,
)
from cli.agent_cli.providers import openai_planner_runtime_pure_helpers_runtime as pure_helpers
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.agent_cli.providers.reference_parity import (
    reference_client_metadata,
    reference_reasoning_summary,
    reference_text_verbosity,
)


def conversation_messages(
    *,
    planner: Any,
    user_text: str,
    history: list[dict[str, str]],
    attachments: list[PromptAttachment] | None = None,
    input_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return planner._conversation_input_items(
        user_text,
        planner._history_for_conversation(history, input_items=input_items),
        attachments=attachments,
        input_items=input_items,
    )


def create_native_tool_session(
    *,
    planner: Any,
    tool_executor: Any,
    prompt_cache_key: str | None = None,
    provider_session_id: str | None = None,
    provider_turn_id: str | None = None,
    provider_sandbox_mode: str | None = None,
    responses_session_cls: Any = OpenAIResponsesSession,
) -> Any:
    reference_parity = bool(planner.reference_parity_enabled)
    return responses_session_cls(
        client=planner.client,
        model=planner.config.model,
        instructions=planner.native_tool_system_prompt,
        tool_specs=planner._tool_specs(),
        provider_name=str(planner.config.provider_name or ""),
        base_url=str(planner.config.base_url or ""),
        reasoning_effort=planner.config.reasoning_effort,
        reasoning_summary=reference_reasoning_summary(planner.config) if reference_parity else None,
        text_verbosity=reference_text_verbosity(planner.config) if reference_parity else None,
        client_metadata=reference_client_metadata(planner.config) if reference_parity else None,
        prompt_cache_key=pure_helpers.stripped_optional_str(prompt_cache_key),
        reference_parity=reference_parity,
        interrupt_requested=getattr(tool_executor, "interrupt_requested", None),
        session_id=pure_helpers.stripped_optional_str(provider_session_id),
        turn_id=pure_helpers.stripped_optional_str(provider_turn_id),
        sandbox_mode=pure_helpers.stripped_optional_str(provider_sandbox_mode),
    )


def create_native_without_tools_session(
    *,
    planner: Any,
    prompt_cache_key: str | None = None,
    provider_session_id: str | None = None,
    provider_turn_id: str | None = None,
    provider_sandbox_mode: str | None = None,
    responses_session_cls: Any = OpenAIResponsesSession,
) -> Any:
    reference_parity = bool(planner.reference_parity_enabled)
    return responses_session_cls(
        client=planner.client,
        model=planner.config.model,
        instructions=planner.native_tool_system_prompt,
        tool_specs=planner._tool_specs(),
        provider_name=str(planner.config.provider_name or ""),
        base_url=str(planner.config.base_url or ""),
        reasoning_effort=planner.config.reasoning_effort,
        reasoning_summary=reference_reasoning_summary(planner.config) if reference_parity else None,
        text_verbosity=reference_text_verbosity(planner.config) if reference_parity else None,
        client_metadata=reference_client_metadata(planner.config) if reference_parity else None,
        prompt_cache_key=pure_helpers.stripped_optional_str(prompt_cache_key),
        reference_parity=reference_parity,
        session_id=pure_helpers.stripped_optional_str(provider_session_id),
        turn_id=pure_helpers.stripped_optional_str(provider_turn_id),
        sandbox_mode=pure_helpers.stripped_optional_str(provider_sandbox_mode),
    )


def build_terminal_handler(
    *,
    planner: Any,
    attachments: list[PromptAttachment] | None = None,
) -> Callable[..., AgentIntent]:
    def _terminal_handler(
        followup_user_text: str,
        executed_events: list[ToolEvent],
        executed_item_events: list[dict[str, Any]] | None = None,
        _previous_response_id: str | None = None,
        _continuation_input_items: list[dict[str, Any]] | None = None,
        initial_send_error: Exception | None = None,
    ) -> AgentIntent:
        if initial_send_error is not None:
            return projection_helpers.fallback_tool_intent(
                executed_events=list(executed_events),
                executed_item_events=executed_item_events,
                compose_turn_events_fn=planner._compose_turn_events,
                failure_reason="final_synthesis_error",
                failure_message=f"{type(initial_send_error).__name__}: {initial_send_error}",
            )
        if planner._synthetic_recovery_allowed():
            try:
                return planner._fresh_synthesis_after_tool_loop(
                    user_text=followup_user_text,
                    executed_events=executed_events,
                    executed_item_events=executed_item_events,
                    attachments=attachments,
                )
            except Exception as exc:
                return projection_helpers.fallback_tool_intent(
                    executed_events=list(executed_events),
                    executed_item_events=executed_item_events,
                    compose_turn_events_fn=planner._compose_turn_events,
                    failure_reason="final_synthesis_error",
                    failure_message=f"{type(exc).__name__}: {exc}",
                )
        return projection_helpers.fallback_tool_intent(
            executed_events=list(executed_events),
            executed_item_events=executed_item_events,
            compose_turn_events_fn=planner._compose_turn_events,
        )

    return _terminal_handler


def build_followup_handler(
    *,
    planner: Any,
    session: Any,
    tool_executor: Any,
    terminal_handler: Callable[..., AgentIntent],
    attachments: list[PromptAttachment] | None = None,
    turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Callable[..., AgentIntent]:
    def _followup_handler(
        followup_user_text: str,
        executed_events: list[ToolEvent],
        executed_item_events: list[dict[str, Any]] | None = None,
        previous_response_id: str | None = None,
        continuation_input_items: list[dict[str, Any]] | None = None,
        initial_send_error: Exception | None = None,
    ) -> AgentIntent:
        if continuation_input_items:
            try:
                return planner._resume_native_tool_followup(
                    session=session,
                    user_text=followup_user_text,
                    tool_executor=tool_executor,
                    executed_events=executed_events,
                    executed_item_events=executed_item_events,
                    previous_response_id=previous_response_id,
                    continuation_input_items=continuation_input_items,
                    initial_send_error=initial_send_error,
                    terminal_handler=terminal_handler,
                    turn_event_callback=turn_event_callback,
                )
            except Exception as exc:
                failure_error = initial_send_error if initial_send_error is not None else exc
                return terminal_handler(
                    followup_user_text,
                    executed_events,
                    executed_item_events,
                    previous_response_id,
                    continuation_input_items,
                    initial_send_error=failure_error,
                )
        if not planner._synthetic_recovery_allowed():
            return terminal_handler(
                followup_user_text,
                executed_events,
                executed_item_events,
                previous_response_id,
                continuation_input_items,
            )
        try:
            return planner._fresh_followup_after_tool_loop(
                user_text=followup_user_text,
                executed_events=executed_events,
                tool_executor=tool_executor,
                executed_item_events=executed_item_events,
                attachments=attachments,
            )
        except Exception:
            return terminal_handler(
                followup_user_text,
                executed_events,
                executed_item_events,
                previous_response_id,
                continuation_input_items,
            )

    return _followup_handler


def run_turn_engine_with_active_session(
    *,
    planner: Any,
    session: Any,
    user_text: str,
    initial_input: list[dict[str, Any]],
    tool_executor: Any,
    turn_event_callback: Callable[[dict[str, Any]], None] | None,
    followup_handler: Callable[..., AgentIntent],
    terminal_handler: Callable[..., AgentIntent],
    prompt_cache_key: str | None = None,
    initial_previous_response_id: str | None = None,
    turn_engine_cls: Any = TurnEngine,
) -> AgentIntent:
    engine = turn_engine_cls(
        session,
        tool_executor=tool_executor,
        command_builder=planner._command_for_function_call,
        followup_handler=followup_handler,
        terminal_handler=terminal_handler,
        turn_event_callback=turn_event_callback,
    )
    planner.register_active_stream_session(session)
    try:
        return engine.run(
            user_text=user_text,
            initial_input=initial_input,
            initial_previous_response_id=initial_previous_response_id,
            prompt_cache_key=pure_helpers.stripped_optional_str(prompt_cache_key),
        )
    finally:
        planner.clear_active_stream_session(session)


def send_without_tools_with_active_session(
    *,
    planner: Any,
    session: Any,
    input_items: list[dict[str, Any]],
    prompt_cache_key: str | None = None,
    turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Any:
    planner.register_active_stream_session(session)
    try:
        return session.send(
            input_items=input_items,
            allow_tools=False,
            prompt_cache_key=pure_helpers.stripped_optional_str(prompt_cache_key),
            turn_event_callback=turn_event_callback,
        )
    finally:
        planner.clear_active_stream_session(session)


__all__ = [
    "build_followup_handler",
    "build_terminal_handler",
    "conversation_messages",
    "create_native_tool_session",
    "create_native_without_tools_session",
    "run_turn_engine_with_active_session",
    "send_without_tools_with_active_session",
]
