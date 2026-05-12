from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.host.plugin_marketplace import PluginMarketplaceEntry
from cli.agent_cli.models import CommandExecutionResult, ToolEvent

from .plugin_marketplace_commands_formatting_helpers_runtime import (
    marketplace_list_text,
    plugins_text,
)
from .plugin_marketplace_commands_status_text_helpers_runtime import (
    entry_action_success_summary,
    entry_action_success_text,
    plugin_install_status_summary,
    plugin_install_status_text,
    plugin_state_change_status_summary,
    plugin_state_change_status_text,
    policy_blocked_text,
)


def result_event(
    name: str,
    *,
    ok: bool,
    summary: str,
    payload: dict[str, Any],
) -> ToolEvent:
    return ToolEvent(name=name, ok=bool(ok), summary=summary, payload=dict(payload))


def plugin_manager_unavailable_result(
    *,
    single_event_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return single_event_result(
        "Plugin manager unavailable.",
        error_event(
            "plugin_marketplace",
            "plugin marketplace unavailable",
            error="plugin manager unavailable",
        ),
        tool_name="plugin_marketplace",
    )


def read_only_blocked_result(
    *,
    action: str,
    single_event_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return single_event_result(
        "Plugin marketplace command blocked.",
        error_event(
            "plugin_marketplace",
            "plugin marketplace command blocked",
            error="runtime sandbox is read-only",
        ),
        arguments={"action": action},
        tool_name="plugin_marketplace",
    )


def marketplace_list_result(
    entries: list[PluginMarketplaceEntry],
    *,
    marketplace_filter: str | None,
    single_event_result: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    payload = {
        "ok": True,
        "count": len(entries),
        "entries": [{**entry.to_dict(), "plugin_key": entry.plugin_key} for entry in entries],
        "marketplace": marketplace_filter,
    }
    return single_event_result(
        marketplace_list_text(entries),
        result_event(
            "plugin_marketplace_list",
            ok=True,
            summary=f"listed {len(entries)} plugin marketplace entries",
            payload=payload,
        ),
        arguments={"marketplace": marketplace_filter},
        tool_name="plugin_marketplace",
    )


def plugins_list_result(
    plugins: list[dict[str, Any]],
    *,
    single_event_result: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    payload = {"ok": True, "plugins": plugins}
    return single_event_result(
        plugins_text(plugins),
        result_event(
            "plugin_marketplace_plugins",
            ok=True,
            summary=f"listed {len(plugins)} plugins",
            payload=payload,
        ),
        tool_name="plugin_marketplace",
    )


def plugin_entry_operation_error_result(
    *,
    action: str,
    error_text: str,
    arguments: dict[str, Any],
    single_event_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return single_event_result(
        f"Plugin marketplace {action} failed: {error_text}",
        error_event(
            f"plugin_marketplace_{action}",
            f"plugin marketplace {action} failed",
            error=error_text,
        ),
        arguments=arguments,
        tool_name="plugin_marketplace",
    )


def plugin_entry_missing_result(
    *,
    action: str,
    plugin_key: str,
    single_event_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return single_event_result(
        f"Plugin marketplace entry not found: {plugin_key}",
        error_event(
            f"plugin_marketplace_{action}",
            f"plugin marketplace {action} failed",
            error="plugin marketplace entry not found",
        ),
        arguments={"plugin_key": plugin_key},
        tool_name="plugin_marketplace",
    )


def plugin_entry_success_result(
    *,
    action: str,
    entry: PluginMarketplaceEntry,
    arguments: dict[str, Any],
    single_event_result: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    payload = {"ok": True, "entry": {**entry.to_dict(), "plugin_key": entry.plugin_key}}
    return single_event_result(
        entry_action_success_text(action, entry.plugin_key),
        result_event(
            f"plugin_marketplace_{action}",
            ok=True,
            summary=entry_action_success_summary(action, entry.plugin_key),
            payload=payload,
        ),
        arguments=arguments,
        tool_name="plugin_marketplace",
    )


def plugin_install_error_result(
    *,
    plugin_key: str,
    replace: bool,
    error_text: str,
    single_event_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return single_event_result(
        f"Plugin marketplace install failed: {error_text}",
        error_event(
            "plugin_marketplace_install",
            "plugin marketplace install failed",
            error=error_text,
        ),
        arguments={"plugin_key": plugin_key, "replace": replace},
        tool_name="plugin_marketplace",
    )


def plugin_install_result(
    *,
    entry: PluginMarketplaceEntry,
    payload: dict[str, Any],
    replace: bool,
    single_event_result: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    ok = bool(payload.get("ok"))
    event = result_event(
        "plugin_marketplace_install",
        ok=ok,
        summary=plugin_install_status_summary(entry.plugin_key, ok),
        payload={**dict(payload), "plugin_key": entry.plugin_key},
    )
    return single_event_result(
        plugin_install_status_text(entry.plugin_key, ok),
        event,
        arguments={"plugin_key": entry.plugin_key, "replace": replace},
        tool_name="plugin_marketplace",
    )


def plugin_state_change_result(
    *,
    action: str,
    plugin_ref: str,
    payload: dict[str, Any],
    single_event_result: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    ok = bool(payload.get("ok"))
    return single_event_result(
        plugin_state_change_status_text(action, plugin_ref, ok),
        result_event(
            f"plugin_marketplace_{action}",
            ok=ok,
            summary=plugin_state_change_status_summary(action, plugin_ref, ok),
            payload=dict(payload),
        ),
        arguments={"plugin_name": plugin_ref},
        tool_name="plugin_marketplace",
    )


def policy_blocked_result(
    *,
    action: str,
    plugin_key: str,
    source_value: str | None,
    scope: str | None,
    policy_decision: dict[str, Any],
    single_event_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    error_text = str(policy_decision.get("reason") or "blocked by marketplace policy")
    return single_event_result(
        policy_blocked_text(action, error_text),
        error_event(
            f"plugin_marketplace_{action}",
            f"plugin marketplace {action} blocked by policy",
            error=error_text,
            policy_code=str(policy_decision.get("code") or ""),
            policy_hook=str(policy_decision.get("hook") or ""),
            policy_details=dict(policy_decision.get("details") or {}),
        ),
        arguments={"plugin_key": plugin_key, "path": source_value, "scope": scope},
        tool_name="plugin_marketplace",
    )
