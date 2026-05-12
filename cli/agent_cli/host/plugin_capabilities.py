from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from cli.agent_cli.host import plugin_capability_compat_runtime
from cli.agent_cli.host import plugin_capabilities_runtime

JsonMap = dict[str, Any]


def normalize_provider_tool_spec(item: dict[str, Any]) -> JsonMap | None:
    if not isinstance(item, dict):
        return None
    if item.get("type") == "function" and isinstance(item.get("function"), dict):
        return item
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    description = str(item.get("description") or "").strip()
    parameters = item.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {"type": "object", "properties": {}, "additionalProperties": False}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def hook_items(hooks: Any, name: str) -> list[Any]:
    return plugin_capabilities_runtime.hook_items(hooks, name)


def provider_tool_specs(plugins: list[Any]) -> list[JsonMap]:
    specs: list[JsonMap] = []
    for plugin in plugins:
        if not plugin.is_active():
            continue
        declared_tool_names = plugin_capability_compat_runtime.plugin_declared_model_visible_tool_names(plugin)
        for item in hook_items(plugin.provider_hooks, "tool_specs"):
            model_visible, _reason = plugin_capability_compat_runtime.provider_tool_model_visible(
                item,
                declared_tool_names=declared_tool_names,
            )
            if not model_visible:
                continue
            normalized = normalize_provider_tool_spec(item)
            if normalized is not None:
                specs.append(normalized)
    return specs


def provider_tool_compat_warnings(plugins: list[Any]) -> list[str]:
    return plugin_capability_compat_runtime.collect_hidden_legacy_provider_tool_warnings(
        plugins,
        hook_items_fn=hook_items,
    )


def provider_system_prompt_fragments(plugins: list[Any]) -> list[str]:
    return plugin_capabilities_runtime.hook_text_items(
        plugins,
        hook_name="system_prompt_fragments",
    )


def provider_routing_hints(plugins: list[Any]) -> list[str]:
    return plugin_capabilities_runtime.hook_text_items(
        plugins,
        hook_name="routing_hints",
    )


def effective_skill_roots(plugins: list[Any], *, safe_resolve: Callable[[Path], Path]) -> list[Path]:
    return plugin_capabilities_runtime.effective_skill_roots(
        plugins,
        safe_resolve=safe_resolve,
    )


def effective_mcp_servers(plugins: list[Any]) -> dict[str, JsonMap]:
    return plugin_capabilities_runtime.effective_mcp_servers(plugins)


def user_configured_mcp_servers(merged_config: JsonMap) -> dict[str, JsonMap]:
    configured = merged_config.get("mcp_servers")
    servers: dict[str, JsonMap] = {}
    if isinstance(configured, dict):
        for name, value in configured.items():
            key = str(name or "").strip()
            if key and isinstance(value, dict):
                servers[key] = dict(value)
    return servers


def configured_mcp_servers(*, user_configured: dict[str, JsonMap], effective: dict[str, JsonMap]) -> dict[str, JsonMap]:
    servers: dict[str, JsonMap] = {}
    for name, value in user_configured.items():
        servers[name] = dict(value)
    for name, config in effective.items():
        servers.setdefault(name, dict(config))
    return servers


def effective_apps(plugins: list[Any]) -> list[str]:
    return plugin_capabilities_runtime.effective_apps(plugins)


def effective_app_connectors(plugins: list[Any]) -> list[JsonMap]:
    return plugin_capabilities_runtime.effective_app_connectors(plugins)


def mcp_server_plugin_name(plugins: list[Any], name: str) -> str | None:
    return plugin_capabilities_runtime.mcp_server_plugin_name(plugins, name)


def mcp_server_summaries(
    *,
    plugins: list[Any],
    user_configured: dict[str, JsonMap],
    effective: dict[str, JsonMap],
) -> list[JsonMap]:
    return plugin_capabilities_runtime.mcp_server_summaries(
        plugins=plugins,
        user_configured=user_configured,
        effective=effective,
    )


def gui_bridge_metadata(
    *,
    plugins: list[Any],
    user_configured: dict[str, JsonMap],
    effective: dict[str, JsonMap],
) -> JsonMap:
    return plugin_capabilities_runtime.gui_bridge_metadata(
        plugins=plugins,
        user_configured=user_configured,
        effective=effective,
    )
