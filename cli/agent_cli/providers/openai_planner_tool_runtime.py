from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.models import AgentIntent, CommandExecutionResult, PromptAttachment, ToolEvent
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.agent_cli.providers.openai_planner_followup import (
    _fresh_followup_after_tool_loop as _planner_fresh_followup_after_tool_loop,
    _fresh_synthesis_after_tool_loop as _planner_fresh_synthesis_after_tool_loop,
    _merge_followup_synthesis_intent as _planner_merge_followup_synthesis_intent,
    _tool_followup_messages as _planner_tool_followup_messages,
)
from cli.agent_cli.providers.openai_planner_turn_events import (
    _canonical_turn_events as _planner_canonical_turn_events,
    _compose_turn_events as _planner_compose_turn_events,
    _next_item_index as _planner_next_item_index,
    _rebase_item_events as _planner_rebase_item_events,
    _rewrite_existing_turn_events as _planner_rewrite_existing_turn_events,
    _tool_item_events_from_turn_events as _planner_tool_item_events_from_turn_events,
    _tool_output_item as _planner_tool_output_item,
)
from cli.agent_cli.providers import openai_planner_tool_helpers_runtime

PlannerToolExecutor = Callable[[str], Tuple[str, List[ToolEvent]]]


def _response_function_calls(response: Any) -> List[Dict[str, Any]]:
    return openai_planner_tool_helpers_runtime.response_function_calls(response)


def _response_output_text(response: Any) -> str:
    return openai_planner_tool_helpers_runtime.response_output_text(response)


def _tool_output_item(call_id: str, command_text: Optional[str], assistant_text: str, events: List[ToolEvent]) -> Dict[str, Any]:
    return _planner_tool_output_item(call_id, command_text, assistant_text, events)


def _next_item_index(events: List[Dict[str, Any]]) -> int:
    return _planner_next_item_index(events)


def _rebase_item_events(events: List[Dict[str, Any]], *, start_index: int) -> List[Dict[str, Any]]:
    return _planner_rebase_item_events(events, start_index=start_index)


def _compose_turn_events(
    *,
    assistant_text: str,
    response_items: List[Any],
    executed_item_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return _planner_compose_turn_events(
        assistant_text=assistant_text,
        response_items=response_items,
        executed_item_events=executed_item_events,
    )


def _rewrite_existing_turn_events(
    existing_turn_events: List[Dict[str, Any]],
    *,
    final_text: str,
) -> List[Dict[str, Any]]:
    return _planner_rewrite_existing_turn_events(existing_turn_events, final_text=final_text)


def _canonical_turn_events(
    *,
    assistant_text: str,
    response_items: List[Any],
    executed_item_events: List[Dict[str, Any]],
    existing_turn_events: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    return _planner_canonical_turn_events(
        assistant_text=assistant_text,
        response_items=response_items,
        executed_item_events=executed_item_events,
        existing_turn_events=existing_turn_events,
    )


def _tool_item_events_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _planner_tool_item_events_from_turn_events(turn_events)


def _execute_tool_result(tool_executor: PlannerToolExecutor, command_text: str) -> CommandExecutionResult:
    return openai_planner_tool_helpers_runtime.execute_tool_result(tool_executor, command_text)


def _fresh_synthesis_after_tool_loop(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    log_responses_request_fn: Callable[[str, Dict[str, Any]], None],
    log_responses_response_fn: Callable[[str, Any], None],
) -> AgentIntent:
    return _planner_fresh_synthesis_after_tool_loop(
        planner,
        user_text=user_text,
        executed_events=executed_events,
        executed_item_events=executed_item_events,
        attachments=attachments,
        log_responses_request_fn=log_responses_request_fn,
        log_responses_response_fn=log_responses_response_fn,
    )


def _merge_followup_synthesis_intent(
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
    return _planner_merge_followup_synthesis_intent(
        planner,
        synthesized=synthesized,
        executed_events=executed_events,
        started_at=started_at,
        model_ms=model_ms,
        tool_execution_ms=tool_execution_ms,
        rounds=rounds,
        executed_item_events=executed_item_events,
    )


def _tool_followup_messages(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
) -> List[Dict[str, Any]]:
    return _planner_tool_followup_messages(
        planner,
        user_text=user_text,
        executed_events=executed_events,
        executed_item_events=executed_item_events,
        attachments=attachments,
    )


def _fresh_followup_after_tool_loop(
    planner: Any,
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    tool_executor: PlannerToolExecutor,
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachments: Optional[List[PromptAttachment]] = None,
    log_responses_request_fn: Callable[[str, Dict[str, Any]], None],
    log_responses_response_fn: Callable[[str, Any], None],
) -> AgentIntent:
    return _planner_fresh_followup_after_tool_loop(
        planner,
        user_text=user_text,
        executed_events=executed_events,
        tool_executor=tool_executor,
        executed_item_events=executed_item_events,
        attachments=attachments,
        log_responses_request_fn=log_responses_request_fn,
        log_responses_response_fn=log_responses_response_fn,
    )


def _resume_native_tool_followup(
    planner: Any,
    *,
    session: OpenAIResponsesSession,
    user_text: str,
    tool_executor: PlannerToolExecutor,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    previous_response_id: Optional[str] = None,
    continuation_input_items: Optional[List[Dict[str, Any]]] = None,
    initial_send_error: Optional[Exception] = None,
    terminal_handler: Optional[Callable[..., AgentIntent]] = None,
    turn_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    turn_engine_cls: Any = TurnEngine,
) -> AgentIntent:
    return openai_planner_tool_helpers_runtime.resume_native_tool_followup(
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
