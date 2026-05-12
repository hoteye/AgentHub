from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

JsonMap = dict[str, Any]

_NON_TOOL_TEXT_HOOK_NAMES = frozenset({"system_prompt_fragments", "routing_hints"})
_CONTRACT_OVERRIDE_DIRECTIVE_RE = re.compile(
    r"(?i)\b("
    r"interaction_profile|base_prompt_profile|tool_surface_profile|"
    r"context_prelude_policy|tool_result_projection_policy|continuation_policy|"
    r"turn_protocol_policy|planner_kind|wire_api|reference_parity|codex_parity"
    r")\b\s*(?:=|:|\bis\b)"
)
_PROFILE_FORCE_HINT_RE = re.compile(
    r"(?i)\b(interaction_profile|tool_surface_profile)\b.{0,64}\b(codex_openai|claude_code|generic_chat)\b"
)


def _looks_like_contract_override_directive(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    return bool(
        _CONTRACT_OVERRIDE_DIRECTIVE_RE.search(normalized)
        or _PROFILE_FORCE_HINT_RE.search(normalized)
    )


def active_plugins(plugins: list[Any]) -> list[Any]:
    return [plugin for plugin in plugins if plugin.is_active()]


def hook_items(hooks: Any, name: str) -> list[Any]:
    if hooks is None:
        return []
    if isinstance(hooks, dict):
        items = hooks.get(name) or []
    else:
        items = getattr(hooks, name, []) or []
    return list(items)


def hook_text_items(plugins: list[Any], *, hook_name: str) -> list[str]:
    values: list[str] = []
    enforce_contract_guard = hook_name in _NON_TOOL_TEXT_HOOK_NAMES
    for plugin in active_plugins(plugins):
        for item in hook_items(plugin.provider_hooks, hook_name):
            text = str(item or "").strip()
            if text:
                if enforce_contract_guard and _looks_like_contract_override_directive(text):
                    continue
                values.append(text)
    return values


def effective_skill_roots(plugins: list[Any], *, safe_resolve: Callable[[Path], Path]) -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()
    for plugin in active_plugins(plugins):
        for root in plugin.skill_roots:
            normalized = safe_resolve(root)
            if normalized in seen:
                continue
            seen.add(normalized)
            roots.append(normalized)
    return sorted(roots)


def effective_mcp_servers(plugins: list[Any]) -> dict[str, JsonMap]:
    servers: dict[str, JsonMap] = {}
    for plugin in active_plugins(plugins):
        for name, config in plugin.mcp_servers.items():
            servers.setdefault(name, dict(config))
    return servers


def effective_apps(plugins: list[Any]) -> list[str]:
    apps: list[str] = []
    seen: set[str] = set()
    for plugin in active_plugins(plugins):
        for connector in plugin.apps:
            connector_id = str(connector.get("connector_id") or connector.get("connector_key") or "").strip()
            if not connector_id or connector_id in seen:
                continue
            seen.add(connector_id)
            apps.append(connector_id)
    return apps


def normalize_app_connector(*, plugin: Any, connector: JsonMap, connector_id: str) -> JsonMap:
    return {
        "connector_id": connector_id,
        "connector_key": connector_id,
        "display_name": connector.get("display_name") or connector_id,
        "plugin_name": plugin.plugin_name,
        "description": connector.get("description") or "",
        "connector_kind": connector.get("connector_kind") or "app",
        "supports_webhook": bool(connector.get("supports_webhook")),
        "supports_polling": bool(connector.get("supports_polling")),
        "supports_actions": connector.get("supports_actions", True),
        "enabled": True,
        "health": connector.get("health") or "ready",
        "event_types": list(connector.get("event_types") or []),
        "action_types": list(connector.get("action_types") or []),
        "metadata": dict(connector.get("metadata") or {}),
        "source_kind": connector.get("source_kind") or "plugin_app",
    }


def effective_app_connectors(plugins: list[Any]) -> list[JsonMap]:
    connectors: list[JsonMap] = []
    seen: set[str] = set()
    for plugin in active_plugins(plugins):
        for connector in plugin.apps:
            connector_id = str(connector.get("connector_id") or connector.get("connector_key") or "").strip()
            if not connector_id or connector_id in seen:
                continue
            seen.add(connector_id)
            connectors.append(normalize_app_connector(plugin=plugin, connector=connector, connector_id=connector_id))
    return connectors


def mcp_server_plugin_name(plugins: list[Any], name: str) -> str | None:
    key = str(name or "").strip()
    if not key:
        return None
    for plugin in active_plugins(plugins):
        for server_name in plugin.mcp_servers:
            if str(server_name or "") == key:
                return plugin.plugin_name
    return None


def mcp_server_summaries(
    *,
    plugins: list[Any],
    user_configured: dict[str, JsonMap],
    effective: dict[str, JsonMap],
) -> list[JsonMap]:
    names = sorted(set(user_configured) | set(effective))
    summaries: list[JsonMap] = []
    for name in names:
        config = dict(effective.get(name) or {})
        source = "user" if name in user_configured else "plugin"
        summaries.append(
            {
                "name": name,
                "config": config,
                "source": source,
                "plugin_name": mcp_server_plugin_name(plugins, name),
            }
        )
    return summaries


def gui_bridge_metadata(
    *,
    plugins: list[Any],
    user_configured: dict[str, JsonMap],
    effective: dict[str, JsonMap],
) -> JsonMap:
    return {
        "mcpServers": mcp_server_summaries(plugins=plugins, user_configured=user_configured, effective=effective),
        "appConnectors": effective_app_connectors(plugins),
    }
