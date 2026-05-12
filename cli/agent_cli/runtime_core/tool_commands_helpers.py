from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core.tool_commands_helper_groups import (
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
)
from cli.agent_cli.runtime_core import tool_commands_web_helpers as tool_commands_web_helpers_service

ToolCommandResult = Optional[Tuple[str, List[ToolEvent]] | CommandExecutionResult]


def native_web_search_payload(*args, **kwargs):
    return tool_commands_web_helpers_service.native_web_search_payload(*args, **kwargs)


def _runtime_provider_config(runtime) -> Any | None:
    return tool_commands_web_helpers_service.runtime_provider_config(runtime)


def _anthropic_native_web_search_event(
    runtime,
    *,
    query: str,
    limit: int,
    domains: List[str] | None,
    recency_days: int | None,
    market: str | None,
) -> ToolEvent | None:
    return tool_commands_web_helpers_service.anthropic_native_web_search_event(
        runtime,
        query=query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
        native_web_search_payload_fn=native_web_search_payload,
    )


def _install_runtime_web_search_provider_config(runtime) -> Callable[[], None]:
    return tool_commands_web_helpers_service.install_runtime_web_search_provider_config(runtime)


def handle_web_search(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
    error_event: Callable[..., ToolEvent] | None = None,
) -> ToolCommandResult:
    return tool_commands_web_helpers_service.handle_web_search(
        runtime,
        arg_text=arg_text,
        call_structured=call_structured,
        single_event_result=single_event_result,
        text_only_result=text_only_result,
        command_usage_text=command_usage_text,
        error_event=error_event,
        install_runtime_web_search_provider_config_fn=_install_runtime_web_search_provider_config,
    )


def handle_web_fetch(
    runtime,
    *,
    arg_text: str,
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    command_usage_text: Callable[[str], str],
) -> ToolCommandResult:
    return tool_commands_web_helpers_service.handle_web_fetch(
        runtime,
        arg_text=arg_text,
        call_structured=call_structured,
        single_event_result=single_event_result,
        text_only_result=text_only_result,
        command_usage_text=command_usage_text,
    )
