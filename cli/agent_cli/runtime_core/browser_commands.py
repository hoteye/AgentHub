from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_core import browser_commands_runtime


def _normalize_browser_act_kind(value: str) -> str:
    return browser_commands_runtime.normalize_browser_act_kind(value)


def _command_action_names(name: str) -> tuple[str, ...]:
    from cli.agent_cli.providers.tool_specs import command_action_names

    return command_action_names(name)


def _browser_usage_text() -> str:
    from cli.agent_cli.providers.tool_specs import command_usage_text

    return command_usage_text("browser") or (
        "Usage: /browser <action> "
        "[status|start|stop|profiles|tabs|open|focus|close|navigate|snapshot|screenshot|pdf|download|wait_download|console|errors|requests|highlight|trace_start|trace_stop|cookies|storage|storage_state|act|evaluate|upload|dialog] "
        "[profile <name>] [transport <local|proxy>] [tab <id>] [url <addr>] [path <rel>] "
        "[ref <id>] [kind <verb>] [paths <a,b>] [time-ms <n>] [method <verb>] [outcome <kind>]"
    )


def handle_browser_command(
    runtime: Any,
    *,
    arg_text: str,
    compact_arguments: Callable[[Dict[str, Any]], Dict[str, Any]],
    text_only_result: Callable[[str], CommandExecutionResult],
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    allowed_actions = set(_command_action_names("browser"))
    parsed_command = browser_commands_runtime.parse_browser_command(
        arg_text,
        text_only_result=text_only_result,
        browser_usage_text=_browser_usage_text,
        allowed_actions=allowed_actions,
    )
    if isinstance(parsed_command, CommandExecutionResult):
        return parsed_command
    action, parsed, extras = parsed_command
    finalized = browser_commands_runtime.finalize_browser_command(
        action,
        parsed,
        extras,
        text_only_result=text_only_result,
    )
    if isinstance(finalized, CommandExecutionResult):
        return finalized
    action, parsed = finalized
    return browser_commands_runtime.browser_tool_result(
        runtime,
        action=action,
        parsed=parsed,
        compact_arguments=compact_arguments,
        call_structured=call_structured,
        single_event_result=single_event_result,
    )
