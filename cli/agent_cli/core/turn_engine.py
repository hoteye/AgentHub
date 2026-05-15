from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from cli.agent_cli.core import turn_engine_facade_runtime as turn_engine_facade_runtime_helpers
from cli.agent_cli.core import turn_engine_helpers as turn_engine_helpers_service
from cli.agent_cli.core import (
    turn_engine_interrupt_runtime as turn_engine_interrupt_runtime_service,
)
from cli.agent_cli.core import (
    turn_engine_run_loop_runtime as turn_engine_run_loop_runtime_service,
)
from cli.agent_cli.core import turn_engine_tool_runtime as turn_engine_tool_runtime_service
from cli.agent_cli.core.provider_session import ProviderSession
from cli.agent_cli.core.turn_engine_facade_runtime import TurnEngineFacadeMixin
from cli.agent_cli.models import (
    AgentIntent,
    ToolEvent,
    tool_event_is_interrupt,
)

FollowupHandler = Callable[..., AgentIntent]
TerminalHandler = Callable[..., AgentIntent]
ToolExecutor = Callable[[str], tuple[str, list[ToolEvent]]]
CommandBuilder = Callable[[str, dict[str, Any]], str | None]

ToolExecutionResult = turn_engine_tool_runtime_service.ToolExecutionResult

_ORCHESTRATION_TRACE_TOOLS = {"spawn_agent", "wait_agent", "agent_workflow", "recover_agent"}
_normalized_trace_number = turn_engine_helpers_service.normalized_trace_number
_normalized_trace_int = turn_engine_helpers_service.normalized_trace_int
_normalized_trace_bool = turn_engine_helpers_service.normalized_trace_bool
_non_empty_trace_text = turn_engine_helpers_service.non_empty_trace_text
_orchestration_outcome_for_event = turn_engine_helpers_service.orchestration_outcome_for_event
_annotate_trace_with_orchestration_outcomes = (
    turn_engine_helpers_service.annotate_trace_with_orchestration_outcomes
)
_orchestration_should_stop = turn_engine_helpers_service.orchestration_should_stop

_planner_trace_delegation_summary = (
    turn_engine_facade_runtime_helpers.planner_trace_delegation_summary
)
_structured_tool_fallback_text = turn_engine_facade_runtime_helpers.structured_tool_fallback_text
_tool_call_preamble_text = turn_engine_facade_runtime_helpers.tool_call_preamble_text
_synthetic_agent_message_event = turn_engine_facade_runtime_helpers.synthetic_agent_message_event
_annotate_tool_events_with_provider_call = (
    turn_engine_facade_runtime_helpers.annotate_tool_events_with_provider_call
)


class TurnEngine(TurnEngineFacadeMixin):
    """Provider-neutral turn runner with tool loop and continuation fallback."""

    def __init__(
        self,
        session: ProviderSession,
        *,
        tool_executor: ToolExecutor,
        command_builder: CommandBuilder | None = None,
        followup_handler: FollowupHandler | None = None,
        terminal_handler: TerminalHandler | None = None,
        tool_batch_runner: (
            Callable[[list[Any]], tuple[list[ToolExecutionResult], int]] | None
        ) = None,
        fallback_on_empty_output: bool = True,
        perf_counter_fn: Callable[[], float] = time.perf_counter,
        max_rounds: int | None = None,
        turn_event_callback: Callable[[dict[str, Any]], None] | None = None,
        pending_input_items_getter: Callable[..., list[dict[str, Any]]] | None = None,
    ) -> None:
        self.session = session
        self.tool_executor = tool_executor
        self.command_builder = command_builder
        self.followup_handler = followup_handler
        self.terminal_handler = terminal_handler
        self.tool_batch_runner = tool_batch_runner
        self.fallback_on_empty_output = fallback_on_empty_output
        self.perf_counter_fn = perf_counter_fn
        self.max_rounds = max(1, int(max_rounds)) if max_rounds is not None else None
        self.turn_event_callback = turn_event_callback
        self.pending_input_items_getter = pending_input_items_getter

    def _interrupt_requested(self) -> bool:
        return turn_engine_helpers_service.interrupt_requested(self.tool_executor)

    def _interrupt_tuple(self) -> tuple[str, list[ToolEvent]]:
        return turn_engine_interrupt_runtime_service.interrupt_tuple(self.tool_executor)

    def _take_pending_input_items(self) -> list[dict[str, Any]]:
        getter = self.pending_input_items_getter
        if not callable(getter):
            return []
        try:
            raw_items = getter()
        except TypeError:
            try:
                raw_items = getter(limit=None)
            except Exception:
                return []
        except Exception:
            return []
        return [dict(item) for item in list(raw_items or []) if isinstance(item, dict)]

    def _uses_incremental_continuation(self) -> bool:
        capability = getattr(self.session, "uses_incremental_continuation", None)
        if not callable(capability):
            return False
        try:
            return bool(capability())
        except Exception:
            return False

    def _interrupted_intent(
        self,
        *,
        executed_events: list[ToolEvent],
        executed_item_events: list[dict[str, Any]],
        model_ms: int,
        tool_execution_ms: int,
        planning_rounds: int,
        planning_trace: list[dict[str, Any]],
        total_ms: int,
    ) -> AgentIntent:
        return turn_engine_helpers_service.interrupted_intent(
            tool_executor=self.tool_executor,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            model_ms=model_ms,
            tool_execution_ms=tool_execution_ms,
            planning_rounds=planning_rounds,
            planning_trace=planning_trace,
            total_ms=total_ms,
            final_intent_builder=self._final_intent,
            tool_event_is_interrupt_fn=tool_event_is_interrupt,
        )

    def run(
        self,
        *,
        user_text: str,
        initial_input: list[dict[str, Any]],
        initial_previous_response_id: str | None = None,
        prompt_cache_key: str | None = None,
        initial_executed_events: list[ToolEvent] | None = None,
        initial_executed_item_events: list[dict[str, Any]] | None = None,
    ) -> AgentIntent:
        return turn_engine_run_loop_runtime_service.run_turn_engine(
            self,
            user_text=user_text,
            initial_input=initial_input,
            initial_previous_response_id=initial_previous_response_id,
            prompt_cache_key=prompt_cache_key,
            initial_executed_events=initial_executed_events,
            initial_executed_item_events=initial_executed_item_events,
            planner_trace_delegation_summary_fn=_planner_trace_delegation_summary,
            structured_tool_fallback_text_fn=_structured_tool_fallback_text,
            tool_call_preamble_text_fn=_tool_call_preamble_text,
            synthetic_agent_message_event_fn=_synthetic_agent_message_event,
            annotate_trace_with_orchestration_outcomes_fn=(
                _annotate_trace_with_orchestration_outcomes
            ),
            orchestration_should_stop_fn=_orchestration_should_stop,
        )

    def _execute_tool_calls(
        self,
        tool_calls: list[Any],
        *,
        initial_item_events: list[dict[str, Any]] | None = None,
    ) -> tuple[list[ToolExecutionResult], int]:
        return turn_engine_tool_runtime_service.execute_tool_calls(
            self,
            tool_calls,
            initial_item_events=initial_item_events,
        )


def _compose_turn_events(
    *, assistant_text: str, response_items: list[Any], executed_item_events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return turn_engine_helpers_service.compose_turn_events(
        assistant_text=assistant_text,
        response_items=response_items,
        executed_item_events=executed_item_events,
    )
