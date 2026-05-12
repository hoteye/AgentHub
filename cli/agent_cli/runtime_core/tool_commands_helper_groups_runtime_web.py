from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core import tool_commands_runtime as tool_commands_runtime_service
from cli.agent_cli.runtime_core.tool_commands_params_runtime import parse_click_args, parse_find_args, parse_open_args

ToolCommandResult = Optional[Tuple[str, List[ToolEvent]] | CommandExecutionResult]


def handle_open(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    parsed = parse_open_args(runtime._parse_args, arg_text)
    ref = parsed["ref"]
    if not ref:
        return text_only_result(command_usage_text("open") or "Usage: /open <url-or-ref-id> [line <n>]")
    structured = call_structured(runtime.tools, "open_result", ref, line=parsed["line"])
    if structured is not None:
        return structured
    return single_event_result(
        "Open webpage.",
        runtime.tools.open(ref, line=parsed["line"]),
        arguments=parsed,
    )


def handle_click(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    positionals, _ = parse_click_args(runtime._parse_args, arg_text)
    if len(positionals) < 2:
        return text_only_result(command_usage_text("click") or "Usage: /click <ref-id> <id>")
    arguments = tool_commands_runtime_service.click_arguments(positionals)
    structured = call_structured(runtime.tools, "click_result", arguments["ref_id"], id=arguments["id"])
    if structured is not None:
        return structured
    return single_event_result(
        "Open clicked link.",
        runtime.tools.click(arguments["ref_id"], id=arguments["id"]),
        arguments=arguments,
    )


def handle_find(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    positionals, _ = parse_find_args(runtime._parse_args, arg_text)
    if len(positionals) < 2:
        return text_only_result(command_usage_text("find") or "Usage: /find <ref-id> <pattern>")
    arguments = tool_commands_runtime_service.find_arguments(positionals)
    structured = call_structured(runtime.tools, "find_result", arguments["ref_id"], pattern=arguments["pattern"])
    if structured is not None:
        return structured
    return single_event_result(
        "Find text in page.",
        runtime.tools.find(arguments["ref_id"], pattern=arguments["pattern"]),
        arguments=arguments,
    )
