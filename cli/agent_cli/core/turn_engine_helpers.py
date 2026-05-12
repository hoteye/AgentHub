from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.core import turn_engine_facade_runtime as turn_engine_facade_runtime_helpers
from cli.agent_cli.core import turn_engine_interrupt_runtime as turn_engine_interrupt_runtime_service
from cli.agent_cli.core import turn_engine_runtime as turn_engine_runtime_service
from cli.agent_cli.core import turn_engine_trace_runtime as turn_engine_trace_runtime_service
from cli.agent_cli.core import turn_engine_tool_runtime as turn_engine_tool_runtime_service
from cli.agent_cli.models import AgentIntent, ToolEvent

ToolExecutionResult = turn_engine_tool_runtime_service.ToolExecutionResult


def normalized_trace_number(value: Any) -> int | float | None:
    return turn_engine_trace_runtime_service.normalized_trace_number(value)


def normalized_trace_int(value: Any) -> int | None:
    return turn_engine_trace_runtime_service.normalized_trace_int(value)


def normalized_trace_bool(value: Any) -> bool | None:
    return turn_engine_trace_runtime_service.normalized_trace_bool(value)


def non_empty_trace_text(*values: Any) -> str:
    return turn_engine_trace_runtime_service.non_empty_trace_text(*values)


def orchestration_outcome_for_event(event: ToolEvent) -> Dict[str, Any] | None:
    return turn_engine_trace_runtime_service.orchestration_outcome_for_event(event)


def annotate_trace_with_orchestration_outcomes(
    trace_entry: Dict[str, Any],
    execution_results: List[ToolExecutionResult],
    *,
    batch_execution_ms: int,
) -> None:
    turn_engine_trace_runtime_service.annotate_trace_with_orchestration_outcomes(
        trace_entry,
        execution_results,
        batch_execution_ms=batch_execution_ms,
    )
    trace_entry.update(turn_engine_runtime_service.orchestration_budget_timeout_strategy(trace_entry))


def orchestration_should_stop(trace_entry: Dict[str, Any]) -> bool:
    return turn_engine_runtime_service.should_stop_after_orchestration(trace_entry)


def interrupt_requested(tool_executor: Any) -> bool:
    checker = getattr(tool_executor, "interrupt_requested", None)
    if not callable(checker):
        return False
    try:
        return bool(checker())
    except Exception:
        return False


def interrupted_intent(
    *,
    tool_executor: Any,
    executed_events: List[ToolEvent],
    executed_item_events: List[Dict[str, Any]],
    model_ms: int,
    tool_execution_ms: int,
    planning_rounds: int,
    planning_trace: List[Dict[str, Any]],
    total_ms: int,
    final_intent_builder: Any,
    tool_event_is_interrupt_fn: Any,
) -> AgentIntent:
    return turn_engine_interrupt_runtime_service.interrupted_intent(
        tool_executor=tool_executor,
        executed_events=executed_events,
        executed_item_events=executed_item_events,
        model_ms=model_ms,
        tool_execution_ms=tool_execution_ms,
        planning_rounds=planning_rounds,
        planning_trace=planning_trace,
        total_ms=total_ms,
        final_intent_builder=final_intent_builder,
        tool_event_is_interrupt_fn=tool_event_is_interrupt_fn,
    )


def compose_turn_events(
    *,
    assistant_text: str,
    response_items: List[Any],
    executed_item_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return turn_engine_facade_runtime_helpers.compose_turn_events(
        assistant_text=assistant_text,
        response_items=response_items,
        executed_item_events=executed_item_events,
    )
