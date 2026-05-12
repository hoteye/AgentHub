from __future__ import annotations

import shlex
from collections.abc import Callable

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core import tool_commands_runtime as tool_commands_runtime_service
from cli.agent_cli.runtime_core.plugin_marketplace_commands import (
    handle_plugin_marketplace_command,
)
from cli.agent_cli.runtime_core.status_command import status_card_text
from cli.agent_cli.runtime_core.tool_commands_helpers import (
    handle_click,
    handle_file_list,
    handle_file_read,
    handle_file_search,
    handle_find,
    handle_glob_files,
    handle_grep_files,
    handle_list_dir,
    handle_office_run,
    handle_office_skills,
    handle_open,
    handle_plugin_disable,
    handle_plugin_enable,
    handle_plugin_install,
    handle_plugin_reload,
    handle_plugin_remove,
    handle_read_file,
    handle_view_image,
    handle_web_fetch,
    handle_web_search,
)
from cli.agent_cli.runtime_permission_mode import (
    resolve_permission_mode_updates,
    status_with_permission_mode,
)
from cli.agent_cli.runtime_tools_surface_runtime import runtime_tools_capabilities
from cli.agent_cli.slash_parser import SlashInvocation, slash_keyword_map, slash_switch_set


def _runtime_config_permission_mode_option(arg_text: str, options: dict[str, object]) -> str | None:
    direct_value = str(
        options.get("permission-mode") or options.get("permission_mode") or ""
    ).strip()
    if direct_value:
        return direct_value
    try:
        tokens = shlex.split(arg_text, posix=True)
    except ValueError:
        tokens = str(arg_text or "").split()
    for index, token in enumerate(tokens):
        if token not in {"--permission-mode", "--permission_mode"}:
            continue
        if index + 1 >= len(tokens):
            continue
        candidate = str(tokens[index + 1] or "").strip()
        if candidate:
            return candidate
    return None


def _runtime_policy_command_text(
    prefix: str,
    status: dict[str, object],
    *,
    notices: tuple[str, ...] = (),
) -> str:
    rendered = tool_commands_runtime_service.runtime_policy_text(
        prefix, status_with_permission_mode(status)
    )
    notice_lines = [f"note: {str(item).strip()}" for item in notices if str(item).strip()]
    if not notice_lines:
        return rendered
    return "\n".join([rendered, *notice_lines])


def handle_cd_command(
    runtime,
    *,
    name: str,
    arg_text: str,
) -> CommandExecutionResult | None:
    if name != "cd":
        return None
    from pathlib import Path

    path_text = str(arg_text or "").strip().strip("'\"")
    if not path_text:
        current = str(getattr(runtime, "cwd", "") or Path.cwd())
        return CommandExecutionResult(assistant_text=f"Current directory: {current}")
    target = Path(path_text).expanduser().resolve()
    if not target.is_dir():
        return CommandExecutionResult(assistant_text=f"Not a directory: {target}")
    runtime.cwd = target
    import os

    os.chdir(target)
    return CommandExecutionResult(assistant_text=f"Changed directory to {target}")


def handle_runtime_policy_command(
    runtime,
    *,
    name: str,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[ToolEvent]] | CommandExecutionResult | None:
    if name == "status":
        return CommandExecutionResult(assistant_text=status_card_text(runtime))
    if name == "runtime_status":
        status = runtime.runtime_policy_status()
        return (_runtime_policy_command_text("runtime status", dict(status)), [])
    if name == "runtime_config":
        if slash_invocation is not None:
            options = dict(slash_keyword_map(slash_invocation))
            for switch_name in slash_switch_set(slash_invocation):
                options[switch_name] = True
        else:
            _, options = runtime._parse_args(arg_text)
        current_status = dict(runtime.runtime_policy_status() or {})
        current_network_access: str | bool | None = current_status.get("network_access_enabled")
        if current_network_access is None:
            current_network_access = current_status.get("network_access")
        resolution = resolve_permission_mode_updates(
            current_approval_policy=str(current_status.get("approval_policy") or "").strip()
            or None,
            current_sandbox_mode=str(current_status.get("sandbox_mode") or "").strip() or None,
            current_network_access_enabled=current_network_access,
            permission_mode=_runtime_config_permission_mode_option(arg_text, options),
            approval_policy=str(options.get("approval-policy") or "").strip() or None,
            sandbox_mode=str(options.get("sandbox-mode") or "").strip() or None,
            network_access_enabled=str(options.get("network-access") or "").strip() or None,
        )
        status = runtime.configure_runtime_policy(
            approval_policy=resolution.approval_policy,
            sandbox_mode=resolution.sandbox_mode,
            web_search_mode=str(options.get("web-search-mode") or "").strip() or None,
            network_access_enabled=resolution.network_access_enabled,
        )
        return (
            _runtime_policy_command_text(
                "updated runtime policy", dict(status), notices=resolution.notices
            ),
            [],
        )
    return None


def handle_tool_command(
    runtime,
    *,
    name: str,
    arg_text: str,
    command_usage_text: Callable[[str], str],
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> tuple[str, list[ToolEvent]] | CommandExecutionResult | None:
    if name == "tools":
        payload = runtime_tools_capabilities(runtime)
        return (tool_commands_runtime_service.tools_text(payload), [])
    if name == "plugins":
        structured = call_structured(runtime.tools, "list_plugins_result")
        event = (
            structured.tool_events[0]
            if structured and structured.tool_events
            else runtime.tools.list_plugins()
        )
        return tool_commands_runtime_service.plugins_result(event, structured=structured)
    if name.startswith("plugin_marketplace"):
        return handle_plugin_marketplace_command(
            runtime,
            name=name,
            arg_text=arg_text,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            error_event=error_event,
        )
    if name == "plugin_enable":
        return handle_plugin_enable(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            error_event=error_event,
        )
    if name == "plugin_disable":
        return handle_plugin_disable(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            error_event=error_event,
        )
    if name == "plugin_reload":
        return handle_plugin_reload(
            runtime,
            call_structured=call_structured,
            single_event_result=single_event_result,
        )
    if name == "plugin_install":
        return handle_plugin_install(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            error_event=error_event,
        )
    if name == "plugin_remove":
        return handle_plugin_remove(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            error_event=error_event,
        )
    if name == "glob_files":
        return handle_glob_files(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    if name == "grep_files":
        return handle_grep_files(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    if name == "list_dir":
        return handle_list_dir(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    if name == "read_file":
        return handle_read_file(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    if name == "file_list":
        return handle_file_list(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
        )
    if name == "file_search":
        return handle_file_search(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    if name == "file_read":
        return handle_file_read(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    if name == "office_skills":
        return handle_office_skills(
            runtime,
            call_structured=call_structured,
            single_event_result=single_event_result,
        )
    if name == "office_run":
        return handle_office_run(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    if name == "view_image":
        return handle_view_image(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    if name == "web_search":
        return handle_web_search(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
            error_event=error_event,
        )
    if name == "web_fetch":
        return handle_web_fetch(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    if name == "open":
        return handle_open(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    if name == "click":
        return handle_click(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    if name == "find":
        return handle_find(
            runtime,
            arg_text=arg_text,
            call_structured=call_structured,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            command_usage_text=command_usage_text,
        )
    return None
