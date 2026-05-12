from __future__ import annotations

from typing import Any

from cli.agent_cli.host.plugin_marketplace import PluginMarketplaceEntry
from cli.agent_cli.slash_surface import surface_usage_text


def command_usage(action: str) -> str:
    if action == "add":
        return f"Usage: {surface_usage_text('plugin_marketplace_add')}"
    if action == "update":
        return f"Usage: {surface_usage_text('plugin_marketplace_update')}"
    if action == "remove":
        return f"Usage: {surface_usage_text('plugin_marketplace_remove')}"
    if action == "install":
        return f"Usage: {surface_usage_text('plugin_marketplace_install')}"
    if action == "uninstall":
        return f"Usage: {surface_usage_text('plugin_marketplace_uninstall')}"
    if action == "enable":
        return f"Usage: {surface_usage_text('plugin_marketplace_enable')}"
    if action == "disable":
        return f"Usage: {surface_usage_text('plugin_marketplace_disable')}"
    return f"Usage: {surface_usage_text('plugin_marketplace')}"


def marketplace_list_text(entries: list[PluginMarketplaceEntry]) -> str:
    lines = [f"plugin marketplaces: {len(entries)}"]
    for entry in entries:
        lines.append(
            f"- {entry.plugin_key} scope={entry.scope} source={entry.source}"
        )
    return "\n".join(lines)


def plugins_text(plugins: list[dict[str, Any]]) -> str:
    lines = [f"plugins: {len(plugins)}"]
    for item in plugins:
        status = "enabled" if bool(item.get("enabled")) else "disabled"
        lines.append(f"- {item.get('name')} [{status}] v{item.get('version') or '-'}")
    return "\n".join(lines)
