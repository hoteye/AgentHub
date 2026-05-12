from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.models import CommandExecutionResult, ToolEvent, tool_events_to_turn_events
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession, extract_responses_output_text
from cli.agent_cli.providers.error_diagnostics_runtime import normalized_error_text, provider_error_status_code
from cli.agent_cli.providers.planner_postprocessing import sanitize_final_answer_text

PlannerToolExecutor = Callable[[str], Tuple[str, List[ToolEvent]]]
_PREVIOUS_RESPONSE_ID_UNSUPPORTED_MARKERS = (
    "unsupported parameter",
    "unsupported_parameter",
    "unknown parameter",
    "unexpected parameter",
    "unrecognized parameter",
)


def response_function_calls(response: Any) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    for item in list(getattr(response, "output", []) or []):
        if str(getattr(item, "type", "")).strip() != "function_call":
            continue
        arguments_raw = str(getattr(item, "arguments", "") or "{}")
        try:
            arguments = json.loads(arguments_raw)
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append(
            {
                "call_id": str(getattr(item, "call_id", "") or "").strip(),
                "name": str(getattr(item, "name", "") or "").strip(),
                "arguments": arguments,
            }
        )
    return [item for item in calls if item["call_id"] and item["name"]]


def response_output_text(response: Any) -> str:
    return sanitize_final_answer_text(extract_responses_output_text(response))


def execute_tool_result(tool_executor: PlannerToolExecutor, command_text: str) -> CommandExecutionResult:
    structured_runner = getattr(tool_executor, "run_structured", None)
    if callable(structured_runner):
        structured_result = structured_runner(command_text)
    else:
        structured_result = tool_executor(command_text)

    if isinstance(structured_result, CommandExecutionResult):
        return CommandExecutionResult(
            assistant_text=str(structured_result.assistant_text or ""),
            tool_events=list(structured_result.tool_events or []),
            item_events=[
                dict(item)
                for item in list(structured_result.item_events or [])
                if isinstance(item, dict)
            ],
            turn_events=[
                dict(item)
                for item in list(structured_result.turn_events or [])
                if isinstance(item, dict)
            ],
        )

    assistant_text, events = structured_result
    item_events, _ = tool_events_to_turn_events(list(events or []), start_index=0)
    return CommandExecutionResult(
        assistant_text=str(assistant_text or ""),
        tool_events=list(events or []),
        item_events=item_events,
    )


def _previous_response_id_unsupported_error(exc: Exception) -> bool:
    status_code = provider_error_status_code(exc)
    if status_code not in (None, 400, 422):
        return False
    error_text = normalized_error_text(exc)
    if "previous_response_id" not in error_text:
        return False
    return any(marker in error_text for marker in _PREVIOUS_RESPONSE_ID_UNSUPPORTED_MARKERS)


def _disable_session_incremental_continuation(session: Any) -> None:
    disable = getattr(session, "disable_incremental_continuation", None)
    if not callable(disable):
        return
    try:
        disable(reason="previous_response_id_unsupported")
    except Exception:
        return


def resume_native_tool_followup(
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
    terminal_handler: Optional[Callable[..., Any]] = None,
    turn_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    turn_engine_cls: Any = TurnEngine,
) -> Any:
    if not continuation_input_items:
        raise ValueError("native tool follow-up requires continuation_input_items")
    rescue_engine = turn_engine_cls(
        session,
        tool_executor=tool_executor,
        command_builder=planner._command_for_function_call,
        followup_handler=None,
        terminal_handler=terminal_handler,
        turn_event_callback=turn_event_callback,
    )
    initial_input_items = [
        dict(item)
        for item in list(continuation_input_items or [])
        if isinstance(item, dict)
    ]
    initial_executed_item_events = [
        dict(item)
        for item in list(executed_item_events or [])
        if isinstance(item, dict)
    ]

    def _run_rescue(initial_previous_response_id: Optional[str]) -> Any:
        return rescue_engine.run(
            user_text=user_text,
            initial_input=initial_input_items,
            initial_previous_response_id=initial_previous_response_id,
            initial_executed_events=list(executed_events or []),
            initial_executed_item_events=initial_executed_item_events,
        )

    start_without_previous_response_id = bool(
        previous_response_id
        and initial_send_error is not None
        and _previous_response_id_unsupported_error(initial_send_error)
    )
    if start_without_previous_response_id:
        _disable_session_incremental_continuation(session)

    try:
        return _run_rescue(None if start_without_previous_response_id else previous_response_id)
    except Exception as exc:
        if (
            start_without_previous_response_id
            or not previous_response_id
            or not _previous_response_id_unsupported_error(exc)
        ):
            raise
    _disable_session_incremental_continuation(session)
    return _run_rescue(None)
