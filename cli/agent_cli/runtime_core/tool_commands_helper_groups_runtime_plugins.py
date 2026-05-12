from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core import tool_commands_runtime as tool_commands_runtime_service
from cli.agent_cli.runtime_core.tool_commands_params_runtime import parse_plugin_install_args

ToolCommandResult = Optional[Tuple[str, List[ToolEvent]] | CommandExecutionResult]


def handle_plugin_enable(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> ToolCommandResult:
    if not arg_text:
        return "Usage: /plugin_enable <name>", []
    if runtime.workspace_is_read_only():
        return tool_commands_runtime_service.blocked_single_event_result(
            assistant_text="Enable plugin blocked.",
            event_name="plugin_enable",
            summary="plugin enable blocked",
            error="runtime sandbox is read-only",
            arguments={"plugin_name": arg_text},
            error_event=error_event,
            single_event_result=single_event_result,
        )
    structured = call_structured(runtime.tools, "enable_plugin_result", arg_text)
    if structured is not None:
        return structured
    return single_event_result("Enable plugin.", runtime.tools.enable_plugin(arg_text), arguments={"plugin_name": arg_text})


def handle_plugin_disable(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> ToolCommandResult:
    if not arg_text:
        return "Usage: /plugin_disable <name|all>", []
    positionals, options = runtime._parse_args(arg_text)
    normalized_positionals = [str(item or "").strip() for item in list(positionals or []) if str(item or "").strip()]
    disable_all_requested = bool(options.get("all")) or normalized_positionals in (["all"], ["--all"])
    if any(token in {"all", "--all"} for token in normalized_positionals) and not disable_all_requested:
        return "Usage: /plugin_disable <name|all>", []
    if runtime.workspace_is_read_only():
        arguments = {"all": True} if disable_all_requested else {"plugin_name": arg_text}
        return tool_commands_runtime_service.blocked_single_event_result(
            assistant_text="Disable plugins blocked." if disable_all_requested else "Disable plugin blocked.",
            event_name="plugin_disable",
            summary="plugin disable all blocked" if disable_all_requested else "plugin disable blocked",
            error="runtime sandbox is read-only",
            arguments=arguments,
            error_event=error_event,
            single_event_result=single_event_result,
        )
    if disable_all_requested:
        structured = call_structured(runtime.tools, "disable_all_plugins_result")
        if structured is not None:
            return structured
        return single_event_result(
            "Disable all plugins.",
            runtime.tools.disable_all_plugins(),
            arguments={"all": True},
        )
    structured = call_structured(runtime.tools, "disable_plugin_result", arg_text)
    if structured is not None:
        return structured
    return single_event_result("Disable plugin.", runtime.tools.disable_plugin(arg_text), arguments={"plugin_name": arg_text})


def handle_plugin_reload(
    runtime,
    *,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
) -> ToolCommandResult:
    structured = call_structured(runtime.tools, "reload_plugins_result")
    if structured is not None:
        return structured
    return single_event_result("Reload plugins.", runtime.tools.reload_plugins())


def handle_plugin_install(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> ToolCommandResult:
    parsed = parse_plugin_install_args(runtime._parse_args, arg_text)
    path = parsed["path"]
    if not path:
        return "Usage: /plugin_install <zip-or-dir> [replace] [scope <user|project|local|managed>]", []
    if runtime.workspace_is_read_only():
        return tool_commands_runtime_service.blocked_single_event_result(
            assistant_text="Install plugin blocked.",
            event_name="plugin_install",
            summary="plugin install blocked",
            error="runtime sandbox is read-only",
            arguments={"path": path, "replace": parsed["replace"], "scope": parsed["scope"]},
            error_event=error_event,
            single_event_result=single_event_result,
            payload={"path": path},
        )
    structured = call_structured(
        runtime.tools,
        "install_plugin_result",
        path,
        replace=parsed["replace"],
        scope=parsed["scope"],
    )
    if structured is not None:
        return structured
    return single_event_result(
        "Install plugin.",
        runtime.tools.install_plugin(path, replace=parsed["replace"], scope=parsed["scope"]),
        arguments={"path": path, "replace": parsed["replace"], "scope": parsed["scope"]},
    )


def handle_plugin_remove(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> ToolCommandResult:
    if not arg_text:
        return "Usage: /plugin_remove <name>", []
    if runtime.workspace_is_read_only():
        return tool_commands_runtime_service.blocked_single_event_result(
            assistant_text="Remove plugin blocked.",
            event_name="plugin_remove",
            summary="plugin remove blocked",
            error="runtime sandbox is read-only",
            arguments={"plugin_name": arg_text},
            error_event=error_event,
            single_event_result=single_event_result,
        )
    structured = call_structured(runtime.tools, "remove_plugin_result", arg_text)
    if structured is not None:
        return structured
    return single_event_result("Remove plugin.", runtime.tools.remove_plugin(arg_text), arguments={"plugin_name": arg_text})
