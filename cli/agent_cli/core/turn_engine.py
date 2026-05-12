from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from cli.agent_cli.core import turn_engine_facade_runtime as turn_engine_facade_runtime_helpers
from cli.agent_cli.core import turn_engine_helpers as turn_engine_helpers_service
from cli.agent_cli.core import (
    turn_engine_interrupt_runtime as turn_engine_interrupt_runtime_service,
)
from cli.agent_cli.core import turn_engine_round_runtime as turn_engine_round_runtime_service
from cli.agent_cli.core import turn_engine_run_runtime as turn_engine_run_runtime_service
from cli.agent_cli.core import turn_engine_tool_runtime as turn_engine_tool_runtime_service
from cli.agent_cli.core.provider_session import ProviderSession
from cli.agent_cli.core.turn_engine_facade_runtime import TurnEngineFacadeMixin
from cli.agent_cli.models import (
    AgentIntent,
    ToolEvent,
    tool_event_is_interrupt,
    tool_events_include_approval_requests,
)
from cli.agent_cli.runtime_services import approval_continuation_runtime

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
        state = turn_engine_run_runtime_service.initialize_run_state(
            user_text=user_text,
            initial_input=initial_input,
            initial_previous_response_id=initial_previous_response_id,
            initial_executed_events=initial_executed_events,
            initial_executed_item_events=initial_executed_item_events,
        )
        run_started_at = self.perf_counter_fn()
        self._emit_turn_event({"type": "turn.started"})

        while self.max_rounds is None or state.planning_rounds < self.max_rounds:
            if self._interrupt_requested():
                return self._interrupted_intent(
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    model_ms=state.model_ms,
                    tool_execution_ms=state.tool_execution_ms,
                    planning_rounds=state.planning_rounds,
                    planning_trace=state.planning_trace,
                    total_ms=int((self.perf_counter_fn() - run_started_at) * 1000),
                )
            request_started_at = self.perf_counter_fn()
            try:
                step = self.session.send(
                    input_items=state.input_items,
                    allow_tools=state.allow_tools,
                    previous_response_id=state.previous_response_id,
                    prompt_cache_key=prompt_cache_key,
                    turn_event_callback=self.turn_event_callback,
                )
            except Exception as exc:
                if state.previous_response_id and state.executed_events and self.followup_handler:
                    fallback = self._invoke_handler(
                        self.followup_handler,
                        user_text=user_text,
                        executed_events=state.executed_events,
                        executed_item_events=state.executed_item_events,
                        previous_response_id=state.previous_response_id,
                        continuation_input_items=state.replay_input_items,
                        initial_send_error=exc,
                    )
                    return self._fallback_intent(
                        fallback,
                        executed_events=state.executed_events,
                        executed_item_events=state.executed_item_events,
                        model_ms=state.model_ms,
                        tool_execution_ms=state.tool_execution_ms,
                        planning_rounds=state.planning_rounds,
                        total_ms=int((self.perf_counter_fn() - run_started_at) * 1000),
                    )
                if state.previous_response_id and state.executed_events and self.terminal_handler:
                    fallback = self._invoke_handler(
                        self.terminal_handler,
                        user_text=user_text,
                        executed_events=state.executed_events,
                        executed_item_events=state.executed_item_events,
                        previous_response_id=state.previous_response_id,
                        continuation_input_items=state.replay_input_items,
                        initial_send_error=exc,
                    )
                    return self._fallback_intent(
                        fallback,
                        executed_events=state.executed_events,
                        executed_item_events=state.executed_item_events,
                        model_ms=state.model_ms,
                        tool_execution_ms=state.tool_execution_ms,
                        planning_rounds=state.planning_rounds,
                        total_ms=int((self.perf_counter_fn() - run_started_at) * 1000),
                    )
                raise

            request_elapsed_ms = int((self.perf_counter_fn() - request_started_at) * 1000)
            if self._interrupt_requested():
                return self._interrupted_intent(
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    model_ms=state.model_ms + request_elapsed_ms,
                    tool_execution_ms=state.tool_execution_ms,
                    planning_rounds=state.planning_rounds,
                    planning_trace=state.planning_trace,
                    total_ms=int((self.perf_counter_fn() - run_started_at) * 1000),
                )
            turn_engine_run_runtime_service.record_provider_round(
                state=state,
                step=step,
                request_elapsed_ms=request_elapsed_ms,
                trace_entry_builder=turn_engine_round_runtime_service.build_trace_entry,
                summary_builder=_planner_trace_delegation_summary,
                record_round_items_fn=turn_engine_round_runtime_service.record_tool_call_round_items,
                emit_turn_event_fn=self._emit_turn_event,
                preamble_text_builder=_tool_call_preamble_text,
                synthetic_event_builder=_synthetic_agent_message_event,
            )
            terminal_resolution = turn_engine_round_runtime_service.resolve_terminal_round(
                step=step,
                interrupt_requested=self._interrupt_requested(),
                fallback_on_empty_output=self.fallback_on_empty_output,
                executed_events=state.executed_events,
                executed_item_events=state.executed_item_events,
                terminal_handler=self.terminal_handler,
                user_text=user_text,
                previous_response_id=state.previous_response_id,
                continuation_input_items=state.input_items,
                model_ms=state.model_ms,
                tool_execution_ms=state.tool_execution_ms,
                planning_rounds=state.planning_rounds,
                planning_trace=state.planning_trace,
                total_ms_builder=lambda: int((self.perf_counter_fn() - run_started_at) * 1000),
                interrupted_intent_builder=lambda: self._interrupted_intent(
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    model_ms=state.model_ms,
                    tool_execution_ms=state.tool_execution_ms,
                    planning_rounds=state.planning_rounds,
                    planning_trace=state.planning_trace,
                    total_ms=int((self.perf_counter_fn() - run_started_at) * 1000),
                ),
                final_intent_builder=self._final_intent,
                handler_invoker=self._invoke_handler,
                fallback_intent_builder=self._fallback_intent,
                fallback_text_builder=_structured_tool_fallback_text,
            )
            if terminal_resolution is not None:
                return terminal_resolution.intent

            tool_outputs: list[dict[str, Any]] = []
            continuation_input_items = [
                dict(item)
                for item in list(step.continuation_input_items or [])
                if isinstance(item, dict)
            ]
            execution_results, batch_execution_ms = self._execute_tool_calls(
                step.tool_calls,
                initial_item_events=state.executed_item_events,
            )
            tool_outputs, interrupted = (
                turn_engine_run_runtime_service.apply_tool_execution_results(
                    state=state,
                    execution_results=execution_results,
                    batch_execution_ms=batch_execution_ms,
                    emit_turn_events_fn=self._emit_turn_events,
                    session=self.session,
                    interrupt_requested_fn=self._interrupt_requested,
                    annotate_trace_with_orchestration_outcomes_fn=_annotate_trace_with_orchestration_outcomes,
                )
            )
            if interrupted:
                return self._interrupted_intent(
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    model_ms=state.model_ms,
                    tool_execution_ms=state.tool_execution_ms,
                    planning_rounds=state.planning_rounds,
                    planning_trace=state.planning_trace,
                    total_ms=int((self.perf_counter_fn() - run_started_at) * 1000),
                )
            if any(
                tool_events_include_approval_requests(list(result.events or []))
                for result in list(execution_results or [])
            ):
                runtime_owner = approval_continuation_runtime.runtime_from_tool_executor(
                    self.tool_executor
                )
                if runtime_owner is not None:
                    approval_continuation_runtime.attach_pending_tool_continuations_for_results(
                        runtime_owner,
                        execution_results=execution_results,
                        previous_response_id=state.previous_response_id,
                        replay_input_items=state.approval_replay_input_items,
                        continuation_input_items=continuation_input_items,
                        executed_item_events=state.executed_item_events,
                    )
                return self._final_intent(
                    assistant_text=_structured_tool_fallback_text(state.executed_events),
                    response_items=None,
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    model_ms=state.model_ms,
                    tool_execution_ms=state.tool_execution_ms,
                    planning_rounds=state.planning_rounds,
                    planning_trace=state.planning_trace,
                    synthesis_model_ms=0,
                    synthesis_rounds=0,
                    total_ms=int((self.perf_counter_fn() - run_started_at) * 1000),
                )
            pending_input_items = self._take_pending_input_items()
            if state.planning_trace and _orchestration_should_stop(state.planning_trace[-1]):
                incremental_continuation = bool(
                    state.previous_response_id
                    and self._uses_incremental_continuation()
                    and not bool(step.trace.get("provider_native_continuation_pending"))
                )
                next_input_items = turn_engine_round_runtime_service.next_round_input_items(
                    continuation_input_items=continuation_input_items,
                    tool_outputs=tool_outputs,
                    pending_input_items=pending_input_items,
                    incremental_continuation=incremental_continuation,
                )
                if state.executed_events and self.terminal_handler is not None:
                    fallback = self._invoke_handler(
                        self.terminal_handler,
                        user_text=user_text,
                        executed_events=state.executed_events,
                        executed_item_events=state.executed_item_events,
                        previous_response_id=state.previous_response_id,
                        continuation_input_items=next_input_items,
                    )
                    return self._fallback_intent(
                        fallback,
                        executed_events=state.executed_events,
                        executed_item_events=state.executed_item_events,
                        model_ms=state.model_ms,
                        tool_execution_ms=state.tool_execution_ms,
                        planning_rounds=state.planning_rounds,
                        total_ms=int((self.perf_counter_fn() - run_started_at) * 1000),
                    )
                return self._final_intent(
                    assistant_text=_structured_tool_fallback_text(state.executed_events),
                    response_items=None,
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    model_ms=state.model_ms,
                    tool_execution_ms=state.tool_execution_ms,
                    planning_rounds=state.planning_rounds,
                    planning_trace=state.planning_trace,
                    synthesis_model_ms=0,
                    synthesis_rounds=0,
                    total_ms=int((self.perf_counter_fn() - run_started_at) * 1000),
                )
            turn_engine_run_runtime_service.prepare_next_round_input(
                state=state,
                continuation_input_items=continuation_input_items,
                tool_call_items=turn_engine_run_runtime_service.tool_call_replay_items(
                    step.tool_calls
                ),
                tool_outputs=tool_outputs,
                pending_input_items=pending_input_items,
                next_round_input_items_fn=turn_engine_round_runtime_service.next_round_input_items,
                incremental_continuation=bool(
                    state.previous_response_id
                    and self._uses_incremental_continuation()
                    and not bool(step.trace.get("provider_native_continuation_pending"))
                ),
            )

        if state.executed_events and self.terminal_handler is not None:
            fallback = self._invoke_handler(
                self.terminal_handler,
                user_text=user_text,
                executed_events=state.executed_events,
                executed_item_events=state.executed_item_events,
                previous_response_id=state.previous_response_id,
                continuation_input_items=state.replay_input_items,
            )
            return self._fallback_intent(
                fallback,
                executed_events=state.executed_events,
                executed_item_events=state.executed_item_events,
                model_ms=state.model_ms,
                tool_execution_ms=state.tool_execution_ms,
                planning_rounds=state.planning_rounds,
                total_ms=int((self.perf_counter_fn() - run_started_at) * 1000),
            )

        return self._final_intent(
            assistant_text=_structured_tool_fallback_text(state.executed_events),
            response_items=None,
            executed_events=state.executed_events,
            executed_item_events=state.executed_item_events,
            model_ms=state.model_ms,
            tool_execution_ms=state.tool_execution_ms,
            planning_rounds=state.planning_rounds,
            planning_trace=state.planning_trace,
            synthesis_model_ms=0,
            synthesis_rounds=0,
            total_ms=int((self.perf_counter_fn() - run_started_at) * 1000),
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
