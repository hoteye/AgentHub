from __future__ import annotations

from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events


def compact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in dict(arguments or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list | dict) and not value:
            continue
        compact[key] = value
    return compact


def single_event_result(
    assistant_text: str,
    event: ToolEvent,
    *,
    tool_name: str | None = None,
    arguments: dict[str, Any] | None = None,
) -> CommandExecutionResult:
    normalized_arguments = compact_arguments(arguments or {})
    return CommandExecutionResult(
        assistant_text=str(assistant_text or ""),
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name=str(tool_name or event.name or "").strip(),
            arguments=normalized_arguments or None,
            ok=bool(event.ok),
            summary=str(event.summary or ""),
            structured_content=dict(event.payload or {}),
        ),
    )


def invoke_plugin_tool_result(
    runtime_obj,
    *,
    tool_name: str,
    assistant_text: str,
    arguments: dict[str, Any],
    **kwargs: Any,
) -> CommandExecutionResult:
    if runtime_obj is None:
        raise RuntimeError("runtime is required for github plugin commands")
    result_getter = getattr(getattr(runtime_obj, "tools", None), "invoke_plugin_tool_result", None)
    if callable(result_getter):
        result = result_getter(tool_name, **kwargs)
        if isinstance(result, CommandExecutionResult):
            return CommandExecutionResult(
                assistant_text=assistant_text,
                tool_events=list(result.tool_events or []),
                item_events=[
                    dict(item) for item in list(result.item_events or []) if isinstance(item, dict)
                ],
            )
    event = runtime_obj.tools.invoke_plugin_tool(tool_name, **kwargs)
    return single_event_result(
        assistant_text,
        event,
        tool_name=tool_name,
        arguments=arguments,
    )
