from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.models import AgentIntent, PromptAttachment, ToolEvent


def fresh_synthesis_after_tool_loop(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    log_responses_request_fn,
    log_responses_response_fn,
) -> AgentIntent:
    from cli.agent_cli.providers import openai_planner_tool_runtime as openai_planner_tool_runtime_service

    return openai_planner_tool_runtime_service._fresh_synthesis_after_tool_loop(
        planner,
        user_text=user_text,
        executed_events=executed_events,
        executed_item_events=executed_item_events,
        attachments=attachments,
        log_responses_request_fn=log_responses_request_fn,
        log_responses_response_fn=log_responses_response_fn,
    )


def merge_followup_synthesis_intent(
    planner: Any,
    *,
    synthesized: AgentIntent,
    executed_events: List[ToolEvent],
    started_at: float,
    model_ms: int,
    tool_execution_ms: int,
    rounds: int,
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
) -> AgentIntent:
    from cli.agent_cli.providers import openai_planner_tool_runtime as openai_planner_tool_runtime_service

    return openai_planner_tool_runtime_service._merge_followup_synthesis_intent(
        planner,
        synthesized=synthesized,
        executed_events=executed_events,
        started_at=started_at,
        model_ms=model_ms,
        tool_execution_ms=tool_execution_ms,
        rounds=rounds,
        executed_item_events=executed_item_events,
    )


def tool_followup_messages(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
) -> List[Dict[str, Any]]:
    from cli.agent_cli.providers import openai_planner_tool_runtime as openai_planner_tool_runtime_service

    return openai_planner_tool_runtime_service._tool_followup_messages(
        planner,
        user_text=user_text,
        executed_events=executed_events,
        executed_item_events=executed_item_events,
        attachments=attachments,
    )


def fresh_followup_after_tool_loop(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    tool_executor,
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    log_responses_request_fn,
    log_responses_response_fn,
) -> AgentIntent:
    from cli.agent_cli.providers import openai_planner_tool_runtime as openai_planner_tool_runtime_service

    return openai_planner_tool_runtime_service._fresh_followup_after_tool_loop(
        planner,
        user_text=user_text,
        executed_events=executed_events,
        tool_executor=tool_executor,
        executed_item_events=executed_item_events,
        attachments=attachments,
        log_responses_request_fn=log_responses_request_fn,
        log_responses_response_fn=log_responses_response_fn,
    )


def collect_stream_text(
    planner: Any,
    *,
    kwargs: Dict[str, Any],
    call_with_provider_retries_fn,
    attach_responses_503_risks_fn,
    log_responses_request_fn,
    log_responses_response_fn,
) -> str:
    from cli.agent_cli.providers import openai_planner_coordination_runtime as openai_planner_coordination_runtime_helpers

    return openai_planner_coordination_runtime_helpers.collect_stream_text(
        planner=planner,
        kwargs=kwargs,
        call_with_provider_retries_fn=call_with_provider_retries_fn,
        attach_responses_503_risks_fn=attach_responses_503_risks_fn,
        log_responses_request_fn=log_responses_request_fn,
        log_responses_response_fn=log_responses_response_fn,
    )


def synthesis_messages(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
) -> List[Dict[str, Any]]:
    from cli.agent_cli.providers import openai_planner_synthesis as openai_planner_synthesis_helpers

    return openai_planner_synthesis_helpers.synthesis_messages(
        user_text=user_text,
        executed_events=executed_events,
        executed_item_events=executed_item_events,
        attachments=attachments,
        attachment_payloads_fn=planner._attachment_payloads,
    )


def resume_native_tool_followup(
    planner: Any,
    *,
    session: Any,
    user_text: str,
    tool_executor,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    previous_response_id: Optional[str] = None,
    continuation_input_items: Optional[List[Dict[str, Any]]] = None,
    initial_send_error: Optional[Exception] = None,
    terminal_handler: Optional[Callable[..., AgentIntent]] = None,
    turn_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    turn_engine_cls,
) -> AgentIntent:
    from cli.agent_cli.providers import openai_planner_tool_runtime as openai_planner_tool_runtime_service

    return openai_planner_tool_runtime_service._resume_native_tool_followup(
        planner,
        session=session,
        user_text=user_text,
        tool_executor=tool_executor,
        executed_events=executed_events,
        executed_item_events=executed_item_events,
        previous_response_id=previous_response_id,
        continuation_input_items=continuation_input_items,
        initial_send_error=initial_send_error,
        terminal_handler=terminal_handler,
        turn_event_callback=turn_event_callback,
        turn_engine_cls=turn_engine_cls,
    )
