from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cli.agent_cli.core.provider_session import ProviderSessionResult, default_tool_result_items
from cli.agent_cli.core.turn_engine_tool_runtime import ToolExecutionResult
from cli.agent_cli.debug_timeline import (
    log_timeline,
    summarize_input_items_tail,
    timeline_debug_enabled,
)
from cli.agent_cli.models import ResponseInputItem, ToolEvent, tool_events_include_interrupt

_TOOL_OUTPUT_ITEM_TYPES = {
    "function_call_output",
    "custom_tool_call_output",
    "shell_call_output",
    "local_shell_call_output",
}


def _prebuilt_tool_output_items(item_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    seen_call_ids: set[str] = set()
    for raw_event in list(item_events or []):
        if not isinstance(raw_event, dict):
            continue
        if str(raw_event.get("type") or "").strip() != "item.completed":
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() not in _TOOL_OUTPUT_ITEM_TYPES:
            continue
        call_id = str(item.get("call_id") or "").strip()
        if not call_id or call_id in seen_call_ids:
            continue
        seen_call_ids.add(call_id)
        try:
            outputs.append(ResponseInputItem.from_dict(item).to_dict())
        except Exception:
            outputs.append(dict(item))
    return outputs


def _serialized_arguments(arguments: Any) -> str:
    try:
        return json.dumps(arguments if isinstance(arguments, dict) else {}, ensure_ascii=False)
    except TypeError:
        return "{}"


def tool_call_replay_items(tool_calls: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for call in list(tool_calls or []):
        call_id = str(getattr(call, "call_id", "") or "").strip()
        name = str(getattr(call, "name", "") or "").strip()
        if not call_id or not name:
            continue
        arguments = dict(getattr(call, "arguments", {}) or {})
        raw_item = dict(getattr(call, "raw_item", {}) or {})
        item_type = str(
            getattr(call, "item_type", "") or raw_item.get("type") or "function_call"
        ).strip()
        raw_type = str(raw_item.get("type") or item_type).strip()
        normalized_type = raw_type or item_type
        if normalized_type in {"shell_call", "local_shell_call"}:
            item = dict(raw_item)
            item["type"] = normalized_type
            item["call_id"] = call_id
            items.append(item)
            continue
        if normalized_type == "custom_tool_call":
            raw_input = str(raw_item.get("input") or "").strip()
            input_text = (
                raw_input or str(arguments.get("patch") or arguments.get("input") or "").strip()
            )
            if input_text:
                items.append(
                    {
                        "type": "custom_tool_call",
                        "call_id": call_id,
                        "name": name,
                        "input": input_text,
                    }
                )
            continue
        items.append(
            {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": _serialized_arguments(arguments),
            }
        )

    return items


def _item_call_id(item: dict[str, Any]) -> str:
    return str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip()


def _tool_call_ids(items: list[dict[str, Any]]) -> set[str]:
    call_ids: set[str] = set()
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type not in {"function_call", "custom_tool_call", "shell_call", "local_shell_call"}:
            continue
        call_id = _item_call_id(item)
        if call_id:
            call_ids.add(call_id)
    return call_ids


def replay_next_round_input_items(
    *,
    previous_replay_input_items: list[dict[str, Any]],
    continuation_input_items: list[dict[str, Any]],
    tool_call_items: list[dict[str, Any]],
    tool_outputs: list[dict[str, Any]],
    pending_input_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    replay_items = [
        dict(item) for item in list(previous_replay_input_items or []) if isinstance(item, dict)
    ]
    continuation_items = [
        dict(item) for item in list(continuation_input_items or []) if isinstance(item, dict)
    ]
    if continuation_items:
        if (
            len(continuation_items) >= len(replay_items)
            and continuation_items[: len(replay_items)] == replay_items
        ):
            replay_items = continuation_items
        else:
            replay_items.extend(continuation_items)

    seen_call_ids = _tool_call_ids(replay_items)
    for item in list(tool_call_items or []):
        if not isinstance(item, dict):
            continue
        call_id = _item_call_id(item)
        if call_id and call_id in seen_call_ids:
            continue
        if call_id:
            seen_call_ids.add(call_id)
        replay_items.append(dict(item))

    replay_items.extend(dict(item) for item in list(tool_outputs or []) if isinstance(item, dict))
    replay_items.extend(
        dict(item) for item in list(pending_input_items or []) if isinstance(item, dict)
    )
    return replay_items


@dataclass
class TurnEngineRunState:
    executed_events: list[ToolEvent] = field(default_factory=list)
    executed_item_events: list[dict[str, Any]] = field(default_factory=list)
    tool_execution_ms: int = 0
    model_ms: int = 0
    planning_rounds: int = 0
    planning_trace: list[dict[str, Any]] = field(default_factory=list)
    previous_response_id: str | None = None
    allow_tools: bool = True
    input_items: list[dict[str, Any]] = field(default_factory=list)
    replay_input_items: list[dict[str, Any]] = field(default_factory=list)
    approval_replay_input_items: list[dict[str, Any]] = field(default_factory=list)


def initialize_run_state(
    *,
    user_text: str,
    initial_input: list[dict[str, Any]],
    initial_previous_response_id: str | None,
    initial_executed_events: list[ToolEvent] | None,
    initial_executed_item_events: list[dict[str, Any]] | None,
) -> TurnEngineRunState:
    state = TurnEngineRunState(
        executed_events=list(initial_executed_events or []),
        executed_item_events=[
            dict(item)
            for item in list(initial_executed_item_events or [])
            if isinstance(item, dict)
        ],
        previous_response_id=initial_previous_response_id,
        input_items=list(initial_input),
        replay_input_items=list(initial_input),
        approval_replay_input_items=list(initial_input),
    )
    if timeline_debug_enabled():
        log_timeline(
            "turn_engine.run.begin",
            user_text=user_text,
            input_count=len(state.input_items),
            input_tail=summarize_input_items_tail(state.input_items, tail_len=8),
            initial_event_count=len(state.executed_item_events),
        )
    return state


def record_provider_round(
    *,
    state: TurnEngineRunState,
    step: ProviderSessionResult,
    request_elapsed_ms: int,
    trace_entry_builder: Callable[..., dict[str, Any]],
    summary_builder: Callable[[list[Any]], dict[str, Any]],
    record_round_items_fn: Callable[..., None],
    emit_turn_event_fn: Callable[[dict[str, Any]], None],
    preamble_text_builder: Callable[[str, dict[str, Any]], str],
    synthetic_event_builder: Callable[..., dict[str, Any]],
) -> None:
    if timeline_debug_enabled():
        log_timeline(
            "turn_engine.round.provider_result",
            response_id=step.response_id,
            tool_call_count=len(step.tool_calls),
            output_text_preview=str(step.output_text or "")[:160],
            response_item_count=len(list(step.response_items or [])),
            model_elapsed_ms=request_elapsed_ms,
            provider_native_continuation_pending=bool(
                step.trace.get("provider_native_continuation_pending")
            ),
            provider_native_continuation_reason=str(
                step.trace.get("provider_native_continuation_reason") or ""
            ),
        )
    state.model_ms += request_elapsed_ms
    state.planning_rounds += 1
    state.previous_response_id = step.response_id
    state.planning_trace.append(
        trace_entry_builder(
            planning_round=state.planning_rounds,
            request_elapsed_ms=request_elapsed_ms,
            step=step,
            summary_builder=summary_builder,
        )
    )
    record_round_items_fn(
        step=step,
        executed_item_events=state.executed_item_events,
        emit_turn_event=emit_turn_event_fn,
        preamble_text_builder=preamble_text_builder,
        synthetic_event_builder=synthetic_event_builder,
    )


def apply_tool_execution_results(
    *,
    state: TurnEngineRunState,
    execution_results: list[ToolExecutionResult],
    batch_execution_ms: int,
    emit_turn_events_fn: Callable[[list[dict[str, Any]]], None],
    session: Any,
    interrupt_requested_fn: Callable[[], bool],
    annotate_trace_with_orchestration_outcomes_fn: Callable[..., None],
) -> tuple[list[dict[str, Any]], bool]:
    if timeline_debug_enabled():
        log_timeline(
            "turn_engine.round.tool_batch.completed",
            result_count=len(execution_results),
            batch_execution_ms=batch_execution_ms,
        )
    state.tool_execution_ms += batch_execution_ms
    tool_outputs: list[dict[str, Any]] = []
    for result in execution_results:
        events = list(result.events)
        for event in list(events):
            payload = event.payload if isinstance(event.payload, dict) else {}
            payload.setdefault("planner_elapsed_ms", result.elapsed_ms)
            event.payload = payload
        state.executed_events.extend(events)
        item_events = [
            dict(item) for item in list(result.item_events or []) if isinstance(item, dict)
        ]
        state.executed_item_events.extend(item_events)
        emit_turn_events_fn(
            _events_not_already_emitted(
                item_events,
                list(getattr(result, "pre_emitted_item_events", None) or []),
            )
        )
        items = _prebuilt_tool_output_items(item_events)
        if not items:
            item_builder = getattr(session, "build_tool_result_items", None)
            items = (
                item_builder(
                    call_id=result.call_id,
                    command_text=result.command_text,
                    assistant_text=result.assistant_text,
                    events=events,
                )
                if callable(item_builder)
                else default_tool_result_items(
                    call_id=result.call_id,
                    command_text=result.command_text,
                    assistant_text=result.assistant_text,
                    events=events,
                )
            )
        tool_outputs.extend(list(items or []))
        if interrupt_requested_fn() or tool_events_include_interrupt(events):
            return tool_outputs, True
    if state.planning_trace:
        annotate_trace_with_orchestration_outcomes_fn(
            state.planning_trace[-1],
            execution_results,
            batch_execution_ms=batch_execution_ms,
        )
    return tool_outputs, False


def _events_not_already_emitted(
    item_events: list[dict[str, Any]],
    pre_emitted_item_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not pre_emitted_item_events:
        return item_events
    skipped_signatures = {
        _item_event_signature(event)
        for event in list(pre_emitted_item_events or [])
        if isinstance(event, dict)
    }
    filtered: list[dict[str, Any]] = []
    for event in list(item_events or []):
        if _item_event_signature(event) in skipped_signatures:
            skipped_signatures.remove(_item_event_signature(event))
            continue
        filtered.append(event)
    return filtered


def _item_event_signature(event: dict[str, Any]) -> tuple[str, str, str, str, str]:
    item = event.get("item") if isinstance(event, dict) else None
    if not isinstance(item, dict):
        return (str((event or {}).get("type") or ""), "", "", "", "")
    return (
        str(event.get("type") or "").strip(),
        str(item.get("type") or "").strip(),
        str(item.get("id") or "").strip(),
        str(item.get("call_id") or "").strip(),
        str(item.get("status") or "").strip(),
    )


def prepare_next_round_input(
    *,
    state: TurnEngineRunState,
    continuation_input_items: list[dict[str, Any]],
    tool_call_items: list[dict[str, Any]],
    tool_outputs: list[dict[str, Any]],
    pending_input_items: list[dict[str, Any]] | None = None,
    next_round_input_items_fn: Callable[..., list[dict[str, Any]]],
    incremental_continuation: bool = False,
) -> None:
    state.approval_replay_input_items = replay_next_round_input_items(
        previous_replay_input_items=state.approval_replay_input_items,
        continuation_input_items=continuation_input_items,
        tool_call_items=tool_call_items,
        tool_outputs=tool_outputs,
        pending_input_items=list(pending_input_items or []),
    )
    state.replay_input_items = next_round_input_items_fn(
        continuation_input_items=continuation_input_items,
        tool_outputs=tool_outputs,
        pending_input_items=list(pending_input_items or []),
        incremental_continuation=False,
    )
    state.input_items = next_round_input_items_fn(
        continuation_input_items=continuation_input_items,
        tool_outputs=tool_outputs,
        pending_input_items=list(pending_input_items or []),
        incremental_continuation=incremental_continuation,
    )
    if timeline_debug_enabled():
        log_timeline(
            "turn_engine.round.next_input",
            previous_response_id=state.previous_response_id,
            continuation_input_count=len(continuation_input_items),
            tool_call_replay_count=len(tool_call_items),
            tool_output_count=len(tool_outputs),
            pending_input_count=len(list(pending_input_items or [])),
            replay_input_count=len(state.replay_input_items),
            approval_replay_input_count=len(state.approval_replay_input_items),
            next_input_count=len(state.input_items),
            next_input_tail=summarize_input_items_tail(state.input_items, tail_len=8),
        )
