from __future__ import annotations

from typing import Any

from cli.agent_cli.models import (
    AgentIntent,
    CommandExecutionResult,
    ToolEvent,
    compose_turn_events_from_response_items,
    default_command_display_text,
    default_response_items,
    tool_event_is_soft_failure,
    tool_events_to_turn_events,
)
from cli.agent_cli.runtime_core.command_dispatch_normalization_helpers_runtime import (
    command_parse_error_result as _command_parse_error_result_helper,
)
from cli.agent_cli.runtime_core.command_dispatch_normalization_helpers_runtime import (
    command_result_from_values as _command_result_from_values_helper,
)
from cli.agent_cli.runtime_core.command_dispatch_normalization_helpers_runtime import (
    command_result_turn_events as _command_result_turn_events_helper,
)
from cli.agent_cli.runtime_core.command_dispatch_normalization_helpers_runtime import (
    normalize_command_result as _normalize_command_result_helper,
)
from cli.agent_cli.runtime_core.command_dispatch_projection_helpers_runtime import (
    tool_result_fallback_text as _tool_result_fallback_text_helper,
)
from cli.agent_cli.runtime_core.command_dispatch_pure_helpers_runtime import (
    final_agent_message_text,
    merge_commentary_text,
    turn_events_include_tool_items,
    unknown_command_assistant_text,
)
from cli.agent_cli.runtime_core.command_handlers import handle_known_command
from cli.agent_cli.runtime_core.command_parsing import split_command
from cli.agent_cli.slash_parser import (
    is_slash_command_text,
    legacy_handler_arg_text,
    parse_slash_invocation,
)


def single_event(prefix: str, event: ToolEvent) -> tuple[str, list[ToolEvent]]:
    return (f"{prefix}\n\n{event.summary}", [event])


def tool_result_fallback_text(events: list[ToolEvent]) -> str:
    return _tool_result_fallback_text_helper(
        events,
        tool_event_is_soft_failure_fn=tool_event_is_soft_failure,
    )


def execute_agent_intent(runtime, intent: AgentIntent) -> tuple[str, list[ToolEvent]]:
    result = execute_agent_intent_result(runtime, intent)
    return result.assistant_text, list(result.tool_events or [])


def execute_agent_intent_result(runtime, intent: AgentIntent) -> CommandExecutionResult:
    assistant_text = intent.assistant_text
    commentary_text = intent.commentary_text
    events: list[ToolEvent] = list(intent.tool_events or [])
    item_events, _ = tool_events_to_turn_events(events, start_index=0)
    turn_events: list[dict] = [
        dict(item) for item in list(intent.turn_events or []) if isinstance(item, dict)
    ]
    if intent.command_text and not turn_events_include_tool_items(turn_events):
        command_result = runtime._run_command_text_result(intent.command_text)
        command_assistant_text = str(command_result.assistant_text or "").strip()
        leading_text = str(assistant_text or "").strip()
        if command_assistant_text:
            if leading_text and leading_text != command_assistant_text:
                commentary_text = merge_commentary_text(commentary_text, leading_text)
            assistant_text = command_assistant_text
        events.extend(list(command_result.tool_events or []))
        item_events.extend(list(command_result.item_events or []))
    canonical_turn_text = final_agent_message_text(turn_events)
    if canonical_turn_text:
        event_display_text = default_command_display_text(assistant_text="", tool_events=events)
        if canonical_turn_text == event_display_text:
            fallback_text = tool_result_fallback_text(events)
            if fallback_text and (
                fallback_text != event_display_text or not str(assistant_text or "").strip()
            ):
                assistant_text = fallback_text
            elif not str(assistant_text or "").strip():
                assistant_text = canonical_turn_text
        else:
            assistant_text = canonical_turn_text
    if events:
        fallback_text = tool_result_fallback_text(events)
        if (not str(assistant_text or "").strip()) and fallback_text:
            assistant_text = fallback_text
    if not turn_events:
        turn_events = _command_result_turn_events(
            assistant_text=assistant_text,
            commentary_text=commentary_text,
            item_events=item_events,
        )
    return CommandExecutionResult(
        assistant_text=assistant_text,
        tool_events=events,
        item_events=item_events,
        turn_events=turn_events,
    )


def run_command_text(runtime, text: str) -> tuple[str, list[ToolEvent]]:
    result = run_command_text_result(runtime, text)
    return result.assistant_text, list(result.tool_events or [])


def run_command_text_result(runtime, text: str) -> CommandExecutionResult:
    try:
        if is_slash_command_text(text):
            return _run_slash_command_text_result(runtime, text)
        name, arg_text = split_command(text)
        result = handle_known_command(runtime, name=name, arg_text=arg_text, text=text)
        if result is not None:
            return _normalize_command_result(result)
        plugin_result_getter = getattr(runtime.tools, "run_plugin_command_result", None)
        plugin_result = (
            plugin_result_getter(name, arg_text, runtime)
            if callable(plugin_result_getter)
            else runtime.tools.run_plugin_command(name, arg_text, runtime)
        )
        if plugin_result is not None:
            return _normalize_command_result(plugin_result)
        assistant_text = unknown_command_assistant_text(name)
        return _command_result_from_values(
            assistant_text=assistant_text,
            command_display_text=assistant_text,
            tool_events=[],
            item_events=[],
            turn_events=[],
            commentary_text="",
        )
    except ValueError as exc:
        return _command_parse_error_result_helper(
            text=text,
            exc=exc,
            tool_events_to_turn_events_fn=tool_events_to_turn_events,
            command_result_turn_events_fn=_command_result_turn_events,
        )


def _run_slash_command_text_result(runtime, text: str) -> CommandExecutionResult:
    invocation = parse_slash_invocation(text, source="runtime")
    compat_arg_text = legacy_handler_arg_text(invocation)
    result = handle_known_command(
        runtime,
        name=invocation.command_name,
        arg_text=compat_arg_text,
        text=text,
        slash_invocation=invocation,
    )
    if result is not None:
        return _with_default_command_display_text(_normalize_command_result(result))
    plugin_result_getter = getattr(runtime.tools, "run_plugin_command_result", None)
    plugin_result = (
        plugin_result_getter(invocation.command_name, invocation.raw_arg_text, runtime)
        if callable(plugin_result_getter)
        else runtime.tools.run_plugin_command(
            invocation.command_name, invocation.raw_arg_text, runtime
        )
    )
    if plugin_result is not None:
        return _with_default_command_display_text(_normalize_command_result(plugin_result))
    assistant_text = unknown_command_assistant_text(invocation.command_name)
    return _command_result_from_values(
        assistant_text=assistant_text,
        command_display_text=assistant_text,
        tool_events=[],
        item_events=[],
        turn_events=[],
        commentary_text="",
    )


def _normalize_command_result(result: Any) -> CommandExecutionResult:
    return _normalize_command_result_helper(
        result,
        tool_events_to_turn_events_fn=tool_events_to_turn_events,
        command_result_turn_events_fn=_command_result_turn_events,
    )


def _with_default_command_display_text(result: CommandExecutionResult) -> CommandExecutionResult:
    display_text = str(getattr(result, "command_display_text", "") or "").strip()
    if not display_text:
        display_text = default_command_display_text(
            assistant_text=str(result.assistant_text or ""),
            tool_events=list(result.tool_events or []),
        )
    if not display_text:
        return result
    return _command_result_from_values(
        assistant_text=str(result.assistant_text or ""),
        command_display_text=display_text,
        tool_events=list(result.tool_events or []),
        item_events=[
            dict(item) for item in list(result.item_events or []) if isinstance(item, dict)
        ],
        turn_events=[
            dict(item) for item in list(result.turn_events or []) if isinstance(item, dict)
        ],
        commentary_text="",
    )


def _command_result_turn_events(
    *,
    assistant_text: str,
    commentary_text: str,
    item_events: list[dict],
) -> list[dict]:
    return _command_result_turn_events_helper(
        assistant_text=assistant_text,
        commentary_text=commentary_text,
        item_events=item_events,
        compose_turn_events_from_response_items_fn=compose_turn_events_from_response_items,
        default_response_items_fn=default_response_items,
    )


def _command_result_from_values(
    *,
    assistant_text: str,
    command_display_text: str = "",
    tool_events: list[ToolEvent],
    item_events: list[dict],
    turn_events: list[dict],
    commentary_text: str,
) -> CommandExecutionResult:
    return _command_result_from_values_helper(
        assistant_text=assistant_text,
        command_display_text=command_display_text,
        tool_events=tool_events,
        item_events=item_events,
        turn_events=turn_events,
        commentary_text=commentary_text,
        command_result_turn_events_fn=_command_result_turn_events,
    )
