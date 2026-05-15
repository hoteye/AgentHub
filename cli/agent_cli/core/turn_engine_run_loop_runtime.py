from __future__ import annotations

from typing import Any

from cli.agent_cli.core import (
    turn_engine_facade_runtime as turn_engine_facade_runtime_helpers,
)
from cli.agent_cli.core import turn_engine_helpers as turn_engine_helpers_service
from cli.agent_cli.core import turn_engine_round_runtime as turn_engine_round_runtime_service
from cli.agent_cli.core import turn_engine_run_runtime as turn_engine_run_runtime_service
from cli.agent_cli.models import (
    AgentIntent,
    ToolEvent,
    tool_events_include_approval_requests,
)
from cli.agent_cli.runtime_services import approval_continuation_runtime

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


def run_turn_engine(
    engine: Any,
    *,
    user_text: str,
    initial_input: list[dict[str, Any]],
    initial_previous_response_id: str | None = None,
    prompt_cache_key: str | None = None,
    initial_executed_events: list[ToolEvent] | None = None,
    initial_executed_item_events: list[dict[str, Any]] | None = None,
    planner_trace_delegation_summary_fn: Any = None,
    structured_tool_fallback_text_fn: Any = None,
    tool_call_preamble_text_fn: Any = None,
    synthetic_agent_message_event_fn: Any = None,
    annotate_trace_with_orchestration_outcomes_fn: Any = None,
    orchestration_should_stop_fn: Any = None,
) -> AgentIntent:
    planner_trace_delegation_summary_fn = (
        planner_trace_delegation_summary_fn or _planner_trace_delegation_summary
    )
    structured_tool_fallback_text_fn = (
        structured_tool_fallback_text_fn or _structured_tool_fallback_text
    )
    tool_call_preamble_text_fn = tool_call_preamble_text_fn or _tool_call_preamble_text
    synthetic_agent_message_event_fn = (
        synthetic_agent_message_event_fn or _synthetic_agent_message_event
    )
    annotate_trace_with_orchestration_outcomes_fn = (
        annotate_trace_with_orchestration_outcomes_fn or _annotate_trace_with_orchestration_outcomes
    )
    orchestration_should_stop_fn = orchestration_should_stop_fn or _orchestration_should_stop
    state = turn_engine_run_runtime_service.initialize_run_state(
        user_text=user_text,
        initial_input=initial_input,
        initial_previous_response_id=initial_previous_response_id,
        initial_executed_events=initial_executed_events,
        initial_executed_item_events=initial_executed_item_events,
    )
    run_started_at = engine.perf_counter_fn()
    engine._emit_turn_event({"type": "turn.started"})

    while engine.max_rounds is None or state.planning_rounds < engine.max_rounds:
        if engine._interrupt_requested():
            return engine._interrupted_intent(
                executed_events=state.executed_events,
                executed_item_events=state.executed_item_events,
                model_ms=state.model_ms,
                tool_execution_ms=state.tool_execution_ms,
                planning_rounds=state.planning_rounds,
                planning_trace=state.planning_trace,
                total_ms=int((engine.perf_counter_fn() - run_started_at) * 1000),
            )
        request_started_at = engine.perf_counter_fn()
        try:
            step = engine.session.send(
                input_items=state.input_items,
                allow_tools=state.allow_tools,
                previous_response_id=state.previous_response_id,
                prompt_cache_key=prompt_cache_key,
                turn_event_callback=engine.turn_event_callback,
            )
        except Exception as exc:
            if state.previous_response_id and state.executed_events and engine.followup_handler:
                fallback = engine._invoke_handler(
                    engine.followup_handler,
                    user_text=user_text,
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    previous_response_id=state.previous_response_id,
                    continuation_input_items=state.replay_input_items,
                    initial_send_error=exc,
                )
                return engine._fallback_intent(
                    fallback,
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    model_ms=state.model_ms,
                    tool_execution_ms=state.tool_execution_ms,
                    planning_rounds=state.planning_rounds,
                    total_ms=int((engine.perf_counter_fn() - run_started_at) * 1000),
                )
            if state.previous_response_id and state.executed_events and engine.terminal_handler:
                fallback = engine._invoke_handler(
                    engine.terminal_handler,
                    user_text=user_text,
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    previous_response_id=state.previous_response_id,
                    continuation_input_items=state.replay_input_items,
                    initial_send_error=exc,
                )
                return engine._fallback_intent(
                    fallback,
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    model_ms=state.model_ms,
                    tool_execution_ms=state.tool_execution_ms,
                    planning_rounds=state.planning_rounds,
                    total_ms=int((engine.perf_counter_fn() - run_started_at) * 1000),
                )
            raise

        request_elapsed_ms = int((engine.perf_counter_fn() - request_started_at) * 1000)
        if engine._interrupt_requested():
            return engine._interrupted_intent(
                executed_events=state.executed_events,
                executed_item_events=state.executed_item_events,
                model_ms=state.model_ms + request_elapsed_ms,
                tool_execution_ms=state.tool_execution_ms,
                planning_rounds=state.planning_rounds,
                planning_trace=state.planning_trace,
                total_ms=int((engine.perf_counter_fn() - run_started_at) * 1000),
            )
        turn_engine_run_runtime_service.record_provider_round(
            state=state,
            step=step,
            request_elapsed_ms=request_elapsed_ms,
            trace_entry_builder=turn_engine_round_runtime_service.build_trace_entry,
            summary_builder=planner_trace_delegation_summary_fn,
            record_round_items_fn=turn_engine_round_runtime_service.record_tool_call_round_items,
            emit_turn_event_fn=engine._emit_turn_event,
            preamble_text_builder=tool_call_preamble_text_fn,
            synthetic_event_builder=synthetic_agent_message_event_fn,
        )
        terminal_resolution = turn_engine_round_runtime_service.resolve_terminal_round(
            step=step,
            interrupt_requested=engine._interrupt_requested(),
            fallback_on_empty_output=engine.fallback_on_empty_output,
            executed_events=state.executed_events,
            executed_item_events=state.executed_item_events,
            terminal_handler=engine.terminal_handler,
            user_text=user_text,
            previous_response_id=state.previous_response_id,
            continuation_input_items=state.input_items,
            model_ms=state.model_ms,
            tool_execution_ms=state.tool_execution_ms,
            planning_rounds=state.planning_rounds,
            planning_trace=state.planning_trace,
            total_ms_builder=lambda: int((engine.perf_counter_fn() - run_started_at) * 1000),
            interrupted_intent_builder=lambda: engine._interrupted_intent(
                executed_events=state.executed_events,
                executed_item_events=state.executed_item_events,
                model_ms=state.model_ms,
                tool_execution_ms=state.tool_execution_ms,
                planning_rounds=state.planning_rounds,
                planning_trace=state.planning_trace,
                total_ms=int((engine.perf_counter_fn() - run_started_at) * 1000),
            ),
            final_intent_builder=engine._final_intent,
            handler_invoker=engine._invoke_handler,
            fallback_intent_builder=engine._fallback_intent,
            fallback_text_builder=structured_tool_fallback_text_fn,
        )
        if terminal_resolution is not None:
            return terminal_resolution.intent

        tool_outputs: list[dict[str, Any]] = []
        continuation_input_items = [
            dict(item)
            for item in list(step.continuation_input_items or [])
            if isinstance(item, dict)
        ]
        execution_results, batch_execution_ms = engine._execute_tool_calls(
            step.tool_calls,
            initial_item_events=state.executed_item_events,
        )
        tool_outputs, interrupted = turn_engine_run_runtime_service.apply_tool_execution_results(
            state=state,
            execution_results=execution_results,
            batch_execution_ms=batch_execution_ms,
            emit_turn_events_fn=engine._emit_turn_events,
            session=engine.session,
            interrupt_requested_fn=engine._interrupt_requested,
            annotate_trace_with_orchestration_outcomes_fn=annotate_trace_with_orchestration_outcomes_fn,
        )
        if interrupted:
            return engine._interrupted_intent(
                executed_events=state.executed_events,
                executed_item_events=state.executed_item_events,
                model_ms=state.model_ms,
                tool_execution_ms=state.tool_execution_ms,
                planning_rounds=state.planning_rounds,
                planning_trace=state.planning_trace,
                total_ms=int((engine.perf_counter_fn() - run_started_at) * 1000),
            )
        if any(
            tool_events_include_approval_requests(list(result.events or []))
            for result in list(execution_results or [])
        ):
            runtime_owner = approval_continuation_runtime.runtime_from_tool_executor(
                engine.tool_executor
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
            return engine._final_intent(
                assistant_text=structured_tool_fallback_text_fn(state.executed_events),
                response_items=None,
                executed_events=state.executed_events,
                executed_item_events=state.executed_item_events,
                model_ms=state.model_ms,
                tool_execution_ms=state.tool_execution_ms,
                planning_rounds=state.planning_rounds,
                planning_trace=state.planning_trace,
                synthesis_model_ms=0,
                synthesis_rounds=0,
                total_ms=int((engine.perf_counter_fn() - run_started_at) * 1000),
            )
        pending_input_items = engine._take_pending_input_items()
        if state.planning_trace and orchestration_should_stop_fn(state.planning_trace[-1]):
            incremental_continuation = bool(
                state.previous_response_id
                and engine._uses_incremental_continuation()
                and not bool(step.trace.get("provider_native_continuation_pending"))
            )
            next_input_items = turn_engine_round_runtime_service.next_round_input_items(
                continuation_input_items=continuation_input_items,
                tool_outputs=tool_outputs,
                pending_input_items=pending_input_items,
                incremental_continuation=incremental_continuation,
            )
            if state.executed_events and engine.terminal_handler is not None:
                fallback = engine._invoke_handler(
                    engine.terminal_handler,
                    user_text=user_text,
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    previous_response_id=state.previous_response_id,
                    continuation_input_items=next_input_items,
                )
                return engine._fallback_intent(
                    fallback,
                    executed_events=state.executed_events,
                    executed_item_events=state.executed_item_events,
                    model_ms=state.model_ms,
                    tool_execution_ms=state.tool_execution_ms,
                    planning_rounds=state.planning_rounds,
                    total_ms=int((engine.perf_counter_fn() - run_started_at) * 1000),
                )
            return engine._final_intent(
                assistant_text=structured_tool_fallback_text_fn(state.executed_events),
                response_items=None,
                executed_events=state.executed_events,
                executed_item_events=state.executed_item_events,
                model_ms=state.model_ms,
                tool_execution_ms=state.tool_execution_ms,
                planning_rounds=state.planning_rounds,
                planning_trace=state.planning_trace,
                synthesis_model_ms=0,
                synthesis_rounds=0,
                total_ms=int((engine.perf_counter_fn() - run_started_at) * 1000),
            )
        turn_engine_run_runtime_service.prepare_next_round_input(
            state=state,
            continuation_input_items=continuation_input_items,
            tool_call_items=turn_engine_run_runtime_service.tool_call_replay_items(step.tool_calls),
            tool_outputs=tool_outputs,
            pending_input_items=pending_input_items,
            next_round_input_items_fn=turn_engine_round_runtime_service.next_round_input_items,
            incremental_continuation=bool(
                state.previous_response_id
                and engine._uses_incremental_continuation()
                and not bool(step.trace.get("provider_native_continuation_pending"))
            ),
        )

    if state.executed_events and engine.terminal_handler is not None:
        fallback = engine._invoke_handler(
            engine.terminal_handler,
            user_text=user_text,
            executed_events=state.executed_events,
            executed_item_events=state.executed_item_events,
            previous_response_id=state.previous_response_id,
            continuation_input_items=state.replay_input_items,
        )
        return engine._fallback_intent(
            fallback,
            executed_events=state.executed_events,
            executed_item_events=state.executed_item_events,
            model_ms=state.model_ms,
            tool_execution_ms=state.tool_execution_ms,
            planning_rounds=state.planning_rounds,
            total_ms=int((engine.perf_counter_fn() - run_started_at) * 1000),
        )

    return engine._final_intent(
        assistant_text=structured_tool_fallback_text_fn(state.executed_events),
        response_items=None,
        executed_events=state.executed_events,
        executed_item_events=state.executed_item_events,
        model_ms=state.model_ms,
        tool_execution_ms=state.tool_execution_ms,
        planning_rounds=state.planning_rounds,
        planning_trace=state.planning_trace,
        synthesis_model_ms=0,
        synthesis_rounds=0,
        total_ms=int((engine.perf_counter_fn() - run_started_at) * 1000),
    )
