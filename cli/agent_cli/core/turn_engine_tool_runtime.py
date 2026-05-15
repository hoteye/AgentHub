from __future__ import annotations

from typing import Any

from cli.agent_cli.core.turn_engine_item_events import (
    _effective_tool_item_name,
    _next_item_index,
    _provisional_started_item_event,
)
from cli.agent_cli.core.turn_engine_tool_runtime_execution_helpers import (
    ToolExecutionResult,
    _provisional_shell_metadata,
    _unmapped_tool_call_result,
    annotate_tool_events_with_provider_call,
)
from cli.agent_cli.core.turn_engine_tool_runtime_execution_helpers import (
    _exec_command_arg_text as _exec_command_arg_text,
)
from cli.agent_cli.core.turn_engine_tool_runtime_execution_helpers import (
    _resolve_runtime_shell as _resolve_runtime_shell,
)
from cli.agent_cli.core.turn_engine_tool_runtime_execution_helpers import (
    synthetic_agent_message_event as synthetic_agent_message_event,
)
from cli.agent_cli.core.turn_engine_tool_runtime_execution_helpers import (
    tool_call_preamble_text as tool_call_preamble_text,
)
from cli.agent_cli.core.turn_engine_tool_runtime_helpers import (
    annotate_raw_item_events_with_provider_call,
    merge_provisional_started_event,
    raw_item_events_for_structured_result,
    rebase_item_events_for_call,
    run_tool_executor_structured,
)
from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.models import (
    AgentIntent,
    ResponseInputItem,
    ToolEvent,
    compose_turn_events_from_response_items,
    default_response_items,
    latest_open_todo_list_item,
    response_items_to_text,
    tool_events_include_approval_requests,
    tool_events_include_interrupt,
)


def execute_tool_calls(
    engine: Any,
    tool_calls: list[Any],
    *,
    initial_item_events: list[dict[str, Any]] | None = None,
) -> tuple[list[ToolExecutionResult], int]:
    if engine.tool_batch_runner is not None:
        batch_results, batch_elapsed_ms = engine.tool_batch_runner(tool_calls)
        return list(batch_results or []), int(batch_elapsed_ms)

    results: list[ToolExecutionResult] = []
    batch_started_at = engine.perf_counter_fn()
    emitted_item_events: list[dict[str, Any]] = [
        dict(item) for item in list(initial_item_events or []) if isinstance(item, dict)
    ]
    next_item_index = _next_item_index(emitted_item_events)
    for call in tool_calls:
        execution_started_at = engine.perf_counter_fn()
        call_name = str(call.name or "")
        call_arguments = dict(call.arguments or {})
        command_text = engine._command_for_call(call_name, call_arguments)
        if not command_text:
            execution_elapsed_ms = int((engine.perf_counter_fn() - execution_started_at) * 1000)
            unmapped_result = _unmapped_tool_call_result(
                call,
                elapsed_ms=execution_elapsed_ms,
            )
            if unmapped_result is not None:
                emitted_item_events.extend(
                    [
                        dict(item)
                        for item in list(unmapped_result.item_events or [])
                        if isinstance(item, dict)
                    ]
                )
                next_item_index = _next_item_index(emitted_item_events)
                results.append(unmapped_result)
            continue
        provisional_shell_metadata = _provisional_shell_metadata(
            engine,
            command_text=command_text,
        )
        active_todo_list = latest_open_todo_list_item(emitted_item_events)
        active_todo_list_id = (
            str(active_todo_list.get("id") or "").strip()
            if isinstance(active_todo_list, dict)
            else ""
        )
        provisional_started = _provisional_started_item_event(
            tool_name=call_name,
            arguments=call_arguments,
            command_text=command_text,
            item_id=f"item_{next_item_index}",
            call_id=str(call.call_id or "").strip(),
            shell_metadata=provisional_shell_metadata,
            active_todo_list_id=active_todo_list_id or None,
        )
        if timeline_debug_enabled():
            log_timeline(
                "turn_engine.tool.provisional_started.emit",
                call_id=getattr(call, "call_id", None),
                tool_name=call_name,
                command_text=command_text,
                item_id=f"item_{next_item_index}",
            )
        engine._emit_turn_event(provisional_started)
        pre_emitted_item_events = [dict(provisional_started)]
        structured_result = run_tool_executor_structured(
            engine,
            call=call,
            command_text=command_text,
        )
        execution_elapsed_ms = int((engine.perf_counter_fn() - execution_started_at) * 1000)
        normalized_tool_name = _effective_tool_item_name(
            tool_name=call_name,
            command_text=command_text,
        )
        annotated_tool_events = annotate_tool_events_with_provider_call(
            tool_events=list(structured_result.tool_events or []),
            provider_call_id=str(call.call_id or "").strip(),
            tool_name=call_name.strip(),
            arguments=call_arguments,
            execution_tool=normalized_tool_name,
            provider_item_type=str(getattr(call, "item_type", "") or "").strip(),
            provider_raw_item=dict(getattr(call, "raw_item", {}) or {}),
        )
        if timeline_debug_enabled():
            log_timeline(
                "turn_engine.tool.execute.end",
                call_id=getattr(call, "call_id", None),
                tool_name=call_name,
                command_text=command_text,
                execution_elapsed_ms=execution_elapsed_ms,
                tool_event_count=len(list(annotated_tool_events or [])),
                raw_item_event_count=len(list(structured_result.item_events or [])),
            )
        raw_item_events = raw_item_events_for_structured_result(structured_result)
        raw_item_events = annotate_raw_item_events_with_provider_call(
            raw_item_events=raw_item_events,
            provider_call_id=str(call.call_id or "").strip(),
            tool_name=call_name.strip(),
            arguments=call_arguments,
        )
        rebased_item_events = rebase_item_events_for_call(
            call_arguments=call_arguments,
            normalized_tool_name=normalized_tool_name,
            active_todo_list_id=active_todo_list_id,
            next_item_index=next_item_index,
            raw_item_events=raw_item_events,
            annotated_tool_events=annotated_tool_events,
        )
        rebased_item_events = merge_provisional_started_event(
            provisional_started,
            rebased_item_events,
            raw_item_events,
        )
        if timeline_debug_enabled():
            log_timeline(
                "turn_engine.tool.item_events.ready",
                call_id=getattr(call, "call_id", None),
                tool_name=call_name,
                rebased_item_event_types=[
                    str(item.get("type") or "")
                    for item in rebased_item_events
                    if isinstance(item, dict)
                ],
            )
        emitted_item_events.extend(
            [dict(item) for item in list(rebased_item_events or []) if isinstance(item, dict)]
        )
        next_item_index = _next_item_index(emitted_item_events)
        results.append(
            ToolExecutionResult(
                call_id=call.call_id,
                command_text=command_text,
                assistant_text=structured_result.assistant_text,
                events=list(annotated_tool_events or []),
                item_events=rebased_item_events,
                elapsed_ms=execution_elapsed_ms,
                pre_emitted_item_events=pre_emitted_item_events,
            )
        )
        if tool_events_include_interrupt(
            annotated_tool_events
        ) or tool_events_include_approval_requests(annotated_tool_events):
            break
    return results, int((engine.perf_counter_fn() - batch_started_at) * 1000)


def compose_turn_events(
    *,
    assistant_text: str,
    response_items: list[ResponseInputItem],
    executed_item_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return compose_turn_events_from_response_items(
        assistant_text=assistant_text,
        response_items=list(response_items or []),
        executed_item_events=[
            dict(item) for item in list(executed_item_events or []) if isinstance(item, dict)
        ],
    )


def final_intent(
    *,
    assistant_text: str,
    response_items: list[ResponseInputItem] | None,
    executed_events: list[ToolEvent],
    executed_item_events: list[dict[str, Any]],
    model_ms: int,
    tool_execution_ms: int,
    planning_rounds: int,
    planning_trace: list[dict[str, Any]],
    synthesis_model_ms: int,
    synthesis_rounds: int,
    total_ms: int,
) -> AgentIntent:
    effective_assistant_text = str(assistant_text or "").strip()
    if not effective_assistant_text and response_items:
        effective_assistant_text = response_items_to_text(list(response_items or []))
    effective_response_items = list(
        response_items or default_response_items(assistant_text=effective_assistant_text)
    )
    turn_events = compose_turn_events(
        assistant_text=effective_assistant_text,
        response_items=effective_response_items,
        executed_item_events=executed_item_events,
    )
    return AgentIntent(
        assistant_text=effective_assistant_text,
        response_items=effective_response_items,
        command_text=None,
        status_hint="tool" if executed_events else "llm",
        tool_events=executed_events,
        turn_events=turn_events,
        timings={
            "initial_model_ms": model_ms,
            "tool_execution_ms": tool_execution_ms,
            "synthesis_model_ms": synthesis_model_ms,
            "total_ms": max(
                int(total_ms),
                model_ms + tool_execution_ms + synthesis_model_ms,
            ),
            "planning_rounds": planning_rounds,
            "synthesis_rounds": synthesis_rounds,
            "planning_trace": planning_trace,
            "synthesis_trace": [],
            "tool_call_count": len(executed_events),
        },
    )


def fallback_intent(
    fallback: AgentIntent,
    *,
    executed_events: list[ToolEvent],
    executed_item_events: list[dict[str, Any]],
    model_ms: int,
    tool_execution_ms: int,
    planning_rounds: int,
    total_ms: int,
) -> AgentIntent:
    fallback_timings = dict(fallback.timings or {})
    fallback_events = list(fallback.tool_events or executed_events)
    merged_initial_model_ms = model_ms + int(fallback_timings.get("initial_model_ms") or 0)
    merged_tool_execution_ms = tool_execution_ms + int(
        fallback_timings.get("tool_execution_ms") or 0
    )
    synthesis_model_ms = int(fallback_timings.get("synthesis_model_ms") or 0)
    effective_total_ms = max(
        int(total_ms),
        merged_initial_model_ms + merged_tool_execution_ms + synthesis_model_ms,
    )
    accounted_ms = merged_initial_model_ms + merged_tool_execution_ms + synthesis_model_ms
    if effective_total_ms > accounted_ms:
        synthesis_model_ms += effective_total_ms - accounted_ms
    synthesis_rounds = int(fallback_timings.get("synthesis_rounds") or 0)
    planning_trace = list(fallback_timings.get("planning_trace") or [])
    synthesis_trace = list(fallback_timings.get("synthesis_trace") or [])
    effective_response_items = list(
        fallback.response_items
        or default_response_items(
            commentary_text=fallback.commentary_text,
            assistant_text=fallback.assistant_text,
        )
    )
    turn_events = list(
        fallback.turn_events
        or compose_turn_events(
            assistant_text=fallback.assistant_text,
            response_items=effective_response_items,
            executed_item_events=executed_item_events,
        )
    )
    return AgentIntent(
        assistant_text=fallback.assistant_text,
        response_items=effective_response_items,
        command_text=fallback.command_text,
        status_hint="tool" if fallback_events else (fallback.status_hint or "llm"),
        tool_events=fallback_events,
        turn_events=turn_events,
        timings={
            "initial_model_ms": merged_initial_model_ms,
            "tool_execution_ms": merged_tool_execution_ms,
            "synthesis_model_ms": synthesis_model_ms,
            "total_ms": effective_total_ms,
            "planning_rounds": planning_rounds,
            "synthesis_rounds": synthesis_rounds,
            "planning_trace": planning_trace,
            "synthesis_trace": synthesis_trace,
            "tool_call_count": len(fallback_events),
        },
    )
