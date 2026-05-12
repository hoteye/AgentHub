from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.models import CommandExecutionResult, ToolEvent

from .plugin_marketplace_commands_formatting_helpers_runtime import command_usage
from .plugin_marketplace_commands_normalization_helpers_runtime import (
    bool_option,
    evaluate_marketplace_policy,
    resolve_source_arg,
)
from .plugin_marketplace_commands_pure_helpers_runtime import marketplace_store
from .plugin_marketplace_commands_result_helpers_runtime import (
    marketplace_list_result,
    plugin_entry_missing_result,
    plugin_entry_operation_error_result,
    plugin_entry_success_result,
    plugin_install_error_result,
    plugin_install_result,
    plugin_manager_unavailable_result,
    plugin_state_change_result,
    plugins_list_result,
    policy_blocked_result,
    read_only_blocked_result,
)


def dispatch_plugin_marketplace_action(
    runtime: Any,
    *,
    manager: Any,
    action: str,
    action_positionals: list[Any],
    options: dict[str, Any],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult | tuple[str, list[ToolEvent]]:
    if action in {"", "list"}:
        return _handle_marketplace_list(
            runtime,
            action_positionals=action_positionals,
            single_event_result=single_event_result,
        )
    if action == "plugins":
        return _handle_plugins_list(manager, single_event_result=single_event_result)
    if runtime.workspace_is_read_only():
        return _read_only_blocked_result(
            action=action,
            single_event_result=single_event_result,
            error_event=error_event,
        )
    store = marketplace_store(runtime)
    if action == "add":
        return _handle_add(
            runtime,
            store=store,
            action_positionals=action_positionals,
            options=options,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            error_event=error_event,
        )
    if action == "update":
        return _handle_update(
            runtime,
            store=store,
            action_positionals=action_positionals,
            options=options,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            error_event=error_event,
        )
    if action == "remove":
        return _handle_remove(
            store=store,
            action_positionals=action_positionals,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            error_event=error_event,
        )
    if action == "install":
        return _handle_install(
            runtime,
            manager=manager,
            store=store,
            action_positionals=action_positionals,
            options=options,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
            error_event=error_event,
        )
    if action in {"uninstall", "enable", "disable"}:
        return _handle_plugin_state_change(
            manager,
            action=action,
            action_positionals=action_positionals,
            single_event_result=single_event_result,
            text_only_result=text_only_result,
        )
    return text_only_result(command_usage(""))


def _handle_marketplace_list(
    runtime: Any,
    *,
    action_positionals: list[Any],
    single_event_result: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    marketplace_filter = str(action_positionals[0] if action_positionals else "").strip() or None
    entries = marketplace_store(runtime).list_entries(marketplace_name=marketplace_filter)
    return marketplace_list_result(
        entries,
        marketplace_filter=marketplace_filter,
        single_event_result=single_event_result,
    )


def _handle_plugins_list(
    manager: Any,
    *,
    single_event_result: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    plugins = list(manager.list_plugins() or [])
    return plugins_list_result(
        plugins,
        single_event_result=single_event_result,
    )


def _read_only_blocked_result(
    *,
    action: str,
    single_event_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return read_only_blocked_result(
        action=action,
        single_event_result=single_event_result,
        error_event=error_event,
    )


def _handle_add(
    runtime: Any,
    *,
    store: Any,
    action_positionals: list[Any],
    options: dict[str, Any],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    if not action_positionals:
        return text_only_result(command_usage("add"))
    plugin_key = str(action_positionals[0] or "").strip()
    source_value = str(
        options.get("path") or (action_positionals[1] if len(action_positionals) > 1 else "")
    ).strip()
    scope = str(options.get("scope") or "project").strip() or "project"
    try:
        resolved_source = resolve_source_arg(source_value, cwd=getattr(runtime, "cwd", None))
        policy_decision = evaluate_marketplace_policy(
            runtime,
            action="add",
            plugin_key=plugin_key,
            source=resolved_source,
            scope=scope,
        )
        if not policy_decision.get("allowed"):
            return policy_blocked_result(
                action="add",
                plugin_key=plugin_key,
                source_value=source_value,
                scope=scope,
                policy_decision=policy_decision,
                single_event_result=single_event_result,
                error_event=error_event,
            )
        entry = store.add_entry(plugin_key, source=resolved_source, scope=scope)
    except ValueError as exc:
        return plugin_entry_operation_error_result(
            action="add",
            error_text=str(exc),
            arguments={"plugin_key": plugin_key, "path": source_value, "scope": scope},
            single_event_result=single_event_result,
            error_event=error_event,
        )
    return plugin_entry_success_result(
        action="add",
        entry=entry,
        arguments={"plugin_key": entry.plugin_key, "path": entry.source, "scope": entry.scope},
        single_event_result=single_event_result,
    )


def _handle_update(
    runtime: Any,
    *,
    store: Any,
    action_positionals: list[Any],
    options: dict[str, Any],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    if not action_positionals:
        return text_only_result(command_usage("update"))
    plugin_key = str(action_positionals[0] or "").strip()
    source_value = str(options.get("path") or "").strip()
    scope = str(options.get("scope") or "").strip()
    try:
        existing_entry = store.get_entry(plugin_key)
        resolved_source = (
            resolve_source_arg(source_value, cwd=getattr(runtime, "cwd", None))
            if source_value
            else None
        )
        policy_decision = evaluate_marketplace_policy(
            runtime,
            action="update",
            plugin_key=plugin_key,
            source=resolved_source or (existing_entry.source if existing_entry else None),
            scope=scope or (existing_entry.scope if existing_entry else None),
        )
        if not policy_decision.get("allowed"):
            return policy_blocked_result(
                action="update",
                plugin_key=plugin_key,
                source_value=source_value or None,
                scope=scope or None,
                policy_decision=policy_decision,
                single_event_result=single_event_result,
                error_event=error_event,
            )
        entry = store.update_entry(plugin_key, source=resolved_source, scope=scope or None)
    except ValueError as exc:
        return plugin_entry_operation_error_result(
            action="update",
            error_text=str(exc),
            arguments={"plugin_key": plugin_key, "path": source_value, "scope": scope or None},
            single_event_result=single_event_result,
            error_event=error_event,
        )
    return plugin_entry_success_result(
        action="update",
        entry=entry,
        arguments={"plugin_key": entry.plugin_key, "path": source_value or None, "scope": scope or None},
        single_event_result=single_event_result,
    )


def _handle_remove(
    *,
    store: Any,
    action_positionals: list[Any],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    if not action_positionals:
        return text_only_result(command_usage("remove"))
    plugin_key = str(action_positionals[0] or "").strip()
    try:
        removed = store.remove_entry(plugin_key)
    except ValueError as exc:
        return plugin_entry_operation_error_result(
            action="remove",
            error_text=str(exc),
            arguments={"plugin_key": plugin_key},
            single_event_result=single_event_result,
            error_event=error_event,
        )
    if removed is None:
        return plugin_entry_missing_result(
            action="remove",
            plugin_key=plugin_key,
            single_event_result=single_event_result,
            error_event=error_event,
        )
    return plugin_entry_success_result(
        action="remove",
        entry=removed,
        arguments={"plugin_key": removed.plugin_key},
        single_event_result=single_event_result,
    )


def _handle_install(
    runtime: Any,
    *,
    manager: Any,
    store: Any,
    action_positionals: list[Any],
    options: dict[str, Any],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    if not action_positionals:
        return text_only_result(command_usage("install"))
    plugin_key = str(action_positionals[0] or "").strip()
    replace = bool_option(options.get("replace"), default=False)
    try:
        source_path = store.resolve_source(plugin_key, cwd=getattr(runtime, "cwd", None))
        entry = store.get_entry(plugin_key)
        if entry is None:
            raise ValueError(f"plugin marketplace entry not found: {plugin_key}")
    except ValueError as exc:
        return plugin_install_error_result(
            plugin_key=plugin_key,
            replace=replace,
            error_text=str(exc),
            single_event_result=single_event_result,
            error_event=error_event,
        )
    payload = manager.install_plugin(
        str(source_path),
        replace=replace,
        marketplace_name=entry.marketplace_name,
        scope=entry.scope,
    )
    return plugin_install_result(
        entry=entry,
        payload=dict(payload),
        replace=replace,
        single_event_result=single_event_result,
    )


def _handle_plugin_state_change(
    manager: Any,
    *,
    action: str,
    action_positionals: list[Any],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
) -> CommandExecutionResult:
    if not action_positionals:
        return text_only_result(command_usage(action))
    plugin_ref = str(action_positionals[0] or "").strip()
    if action == "uninstall":
        payload = manager.remove_plugin(plugin_ref)
    elif action == "enable":
        payload = manager.enable_plugin(plugin_ref)
    else:
        payload = manager.disable_plugin(plugin_ref)
    return plugin_state_change_result(
        action=action,
        plugin_ref=plugin_ref,
        payload=dict(payload),
        single_event_result=single_event_result,
    )
