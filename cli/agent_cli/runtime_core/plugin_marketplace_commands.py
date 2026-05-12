from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple

from cli.agent_cli.models import CommandExecutionResult, ToolEvent

from .plugin_marketplace_commands_normalization_helpers_runtime import (
    parse_plugin_marketplace_action,
)
from .plugin_marketplace_commands_projection_helpers_runtime import (
    dispatch_plugin_marketplace_action,
    plugin_manager_unavailable_result,
)
from .plugin_marketplace_commands_pure_helpers_runtime import plugin_manager


ToolCommandResult = Optional[Tuple[str, List[ToolEvent]] | CommandExecutionResult]


def handle_plugin_marketplace_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> ToolCommandResult:
    if not name.startswith("plugin_marketplace"):
        return None
    manager = plugin_manager(runtime)
    if manager is None:
        return plugin_manager_unavailable_result(
            single_event_result=single_event_result,
            error_event=error_event,
        )
    action, action_positionals, options = parse_plugin_marketplace_action(
        runtime,
        name=name,
        arg_text=arg_text,
    )
    return dispatch_plugin_marketplace_action(
        runtime,
        manager=manager,
        action=action,
        action_positionals=action_positionals,
        options=options,
        single_event_result=single_event_result,
        text_only_result=text_only_result,
        error_event=error_event,
    )
