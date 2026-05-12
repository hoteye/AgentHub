from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.providers.model_routing import STANDARD_DELEGATION_NAMES
from cli.agent_cli.runtime_paths import runtime_project_root
from cli.agent_cli.runtime_tools_surface_runtime import (
    runtime_tools_capabilities as runtime_tools_capabilities_payload,
)
from cli.agent_cli.tools_core.registry import (
    runtime_registry_app_connector_entries,
    runtime_registry_mcp_server_entries,
)


def gui_session_delegate_overrides(runtime: Any) -> dict[str, Any]:
    getter = getattr(getattr(runtime, "agent", None), "session_delegate_overrides", None)
    if not callable(getter):
        return {}
    try:
        payload = getter()
    except Exception:
        return {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def gui_delegate_timeout(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def gui_delegation_snapshot(runtime: Any) -> dict[str, Any]:
    provider_status = dict(getattr(runtime.agent, "provider_status", lambda: {})() or {})
    overrides = gui_session_delegate_overrides(runtime)
    snapshot: dict[str, Any] = {}
    for role_name in STANDARD_DELEGATION_NAMES:
        override = overrides.get(role_name)
        if not isinstance(override, dict):
            override = {}
        snapshot[role_name] = {
            "status": str(provider_status.get(f"delegate_{role_name}") or ""),
            "overrideActive": bool(override),
            "model": str(override.get("model") or ""),
            "provider": str(override.get("provider") or ""),
            "reasoningEffort": str(override.get("reasoning_effort") or ""),
            "timeout": gui_delegate_timeout(override.get("timeout")),
            "source": str(override.get("source") or ""),
        }
    return snapshot


def gui_runtime_policy_status(runtime: Any) -> dict[str, Any]:
    payload = dict(getattr(runtime, "runtime_policy_status", lambda: {})() or {})
    if str(payload.get("network_access") or "").strip().lower() == "disabled":
        payload["network_access"] = "restricted"
    return payload


def runtime_tools_capabilities(runtime: Any) -> dict[str, Any]:
    return runtime_tools_capabilities_payload(runtime)


def plugin_manager_app_connector_entries(
    plugin_manager: Any,
    *,
    runtime_capabilities: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return runtime_registry_app_connector_entries(
        plugin_manager,
        runtime_capabilities=runtime_capabilities,
    )


def normalize_plugin_summary(item: Any) -> dict[str, Any]:
    raw = dict(item or {})
    plugin_id = str(raw.get("plugin_id") or raw.get("name") or raw.get("plugin_name") or "").strip()
    enabled = bool(raw.get("enabled"))
    return {
        "plugin_id": plugin_id,
        "title": str(raw.get("title") or plugin_id or "plugin"),
        "enabled": enabled,
        "health": "ready" if enabled else "warning",
        "description": str(raw.get("description") or ""),
        "version": str(raw.get("version") or ""),
        "plugin_kind": str(raw.get("plugin_kind") or ""),
    }


def tool_events_payload(events: Any) -> list[dict[str, Any]]:
    items = []
    for event in list(events or []):
        items.append(
            {
                "name": str(getattr(event, "name", "") or ""),
                "ok": bool(getattr(event, "ok", False)),
                "summary": str(getattr(event, "summary", "") or ""),
                "payload": dict(getattr(event, "payload", {}) or {}),
            }
        )
    return items


def response_items_payload(items: Any) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in list(items or []):
        to_dict = getattr(item, "to_dict", None)
        if callable(to_dict):
            payload.append(dict(to_dict() or {}))
            continue
        if isinstance(item, dict):
            payload.append(dict(item))
    return payload


def activity_events_payload(events: Any) -> list[dict[str, Any]]:
    items = []
    for event in list(events or []):
        items.append(
            {
                "title": str(getattr(event, "title", "") or ""),
                "status": str(getattr(event, "status", "") or ""),
                "detail": str(getattr(event, "detail", "") or ""),
                "kind": str(getattr(event, "kind", "") or ""),
            }
        )
    return items


def prompt_response_payload(response: Any, *, include_user_text: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "assistant_text": getattr(response, "assistant_text", ""),
        "command_display_text": getattr(response, "command_display_text", ""),
        "commentary_text": getattr(response, "commentary_text", ""),
        "protocol_diagnostics": dict(getattr(response, "protocol_diagnostics", {}) or {}),
        "response_items": response_items_payload(getattr(response, "response_items", []) or []),
        "tool_events": tool_events_payload(getattr(response, "tool_events", []) or []),
        "activity_events": activity_events_payload(getattr(response, "activity_events", []) or []),
        "turn_events": [
            dict(item)
            for item in list(getattr(response, "turn_events", []) or [])
            if isinstance(item, dict)
        ],
    }
    if include_user_text:
        payload["user_text"] = getattr(response, "user_text", "")
    return payload


def thread_history_turn_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item or {})
    payload["timestamp"] = str(payload.get("timestamp") or "")
    payload["user_text"] = str(payload.get("user_text") or "")
    payload["commentary_text"] = str(payload.get("commentary_text") or "")
    payload["assistant_text"] = str(payload.get("assistant_text") or "")
    payload["command_display_text"] = str(payload.get("command_display_text") or "")
    payload["assistant_history_text"] = str(payload.get("assistant_history_text") or "")
    payload["handled_as_command"] = bool(payload.get("handled_as_command"))
    payload["status"] = dict(payload.get("status") or {})
    payload["protocol_diagnostics"] = dict(payload.get("protocol_diagnostics") or {})
    payload["runtime_state"] = dict(payload.get("runtime_state") or {})
    payload["response_items"] = [
        dict(response_item)
        for response_item in list(payload.get("response_items") or [])
        if isinstance(response_item, dict)
    ]
    payload["tool_events"] = [
        {
            "name": str(event.get("name") or ""),
            "ok": bool(event.get("ok")),
            "summary": str(event.get("summary") or ""),
            "payload": dict(event.get("payload") or {}),
        }
        for event in list(payload.get("tool_events") or [])
        if isinstance(event, dict)
    ]
    payload["activity_events"] = [
        {
            "title": str(event.get("title") or ""),
            "status": str(event.get("status") or ""),
            "detail": str(event.get("detail") or ""),
            "kind": str(event.get("kind") or ""),
        }
        for event in list(payload.get("activity_events") or [])
        if isinstance(event, dict)
    ]
    payload["turn_events"] = [
        dict(event) for event in list(payload.get("turn_events") or []) if isinstance(event, dict)
    ]
    payload["reference_context_items"] = [
        dict(context_item)
        for context_item in list(payload.get("reference_context_items") or [])
        if isinstance(context_item, dict)
    ]
    payload["attachments"] = [
        dict(attachment)
        for attachment in list(payload.get("attachments") or [])
        if isinstance(attachment, dict)
    ]
    return payload


def settings_snapshot(runtime: Any) -> dict[str, Any]:
    provider_status = dict(runtime.agent.provider_status() or {})
    available_providers = _available_provider_entries(runtime, provider_status)
    workspace_root = getattr(runtime, "cwd", None) or runtime_project_root() or Path.cwd()
    runtime_capabilities = runtime_tools_capabilities(runtime)
    plugin_manager = getattr(runtime.tools, "_plugin_manager", None)
    workspace_trust = str(runtime_capabilities.get("workspace_trust") or "").strip() or "trusted"
    mcp_servers = runtime_registry_mcp_server_entries(
        plugin_manager, runtime_capabilities=runtime_capabilities
    )
    app_connectors = runtime_registry_app_connector_entries(
        plugin_manager, runtime_capabilities=runtime_capabilities
    )
    delegation_models = gui_delegation_snapshot(runtime)
    if (
        plugin_manager is not None
        and not str(runtime_capabilities.get("workspace_trust") or "").strip()
    ):
        trust_getter = getattr(plugin_manager, "workspace_trust_level", None)
        if callable(trust_getter):
            workspace_trust = str(trust_getter() or "trusted")
    return {
        "model": str(
            provider_status.get("provider_model") or provider_status.get("model_key") or ""
        ),
        "reasoningEffort": str(provider_status.get("provider_reasoning_effort") or ""),
        "delegationModels": delegation_models,
        "delegateOverrideCount": sum(
            1 for item in delegation_models.values() if bool(item.get("overrideActive"))
        ),
        "browserHeadless": bool(getattr(runtime, "_gui_browser_headless", False)),
        "pluginAutoLoad": bool(getattr(runtime, "_gui_plugin_auto_load", True)),
        "workspaceRoot": str(Path(str(workspace_root)).resolve()),
        "workspaceTrust": workspace_trust,
        "providerName": str(provider_status.get("provider_name") or ""),
        "providerLabel": str(provider_status.get("provider_label") or ""),
        "providerStatusState": str(provider_status.get("provider_status_state") or ""),
        "providerStatusReason": str(provider_status.get("provider_status_reason") or ""),
        "availableProviders": available_providers,
        "runtimePolicy": gui_runtime_policy_status(runtime),
        "mcpServers": mcp_servers,
        "appConnectors": app_connectors,
        "runtimeRegistry": {
            "workspaceTrust": workspace_trust,
            "mcpServers": mcp_servers,
            "appConnectors": app_connectors,
            "toolCount": int(runtime_capabilities.get("count") or 0),
            "source": "tools.capabilities" if bool(runtime_capabilities) else "plugin_manager",
        },
    }


def _available_provider_entries(
    runtime: Any, provider_status: dict[str, Any]
) -> list[dict[str, Any]]:
    available_providers = getattr(getattr(runtime, "agent", None), "available_providers", None)
    raw_items: list[Any] = []
    if callable(available_providers):
        try:
            raw_items = list(available_providers() or [])
        except Exception:
            raw_items = []
    current_name = str(provider_status.get("provider_name") or "").strip()
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = str(
            item.get("provider_name")
            or item.get("config_provider_name")
            or item.get("display_name")
            or ""
        ).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        entries.append(
            {
                "providerName": name,
                "configProviderName": str(item.get("config_provider_name") or name),
                "displayName": str(item.get("display_name") or name),
                "defaultModel": str(
                    item.get("provider_default_model_id") or item.get("default_model") or ""
                ),
                "plannerKind": str(item.get("planner_kind") or ""),
                "wireApi": str(item.get("wire_api") or ""),
                "authReady": bool(item.get("provider_auth_ready")),
                "authReason": str(item.get("provider_auth_reason") or ""),
                "statusState": str(item.get("provider_status_state") or ""),
                "statusReason": str(item.get("provider_status_reason") or ""),
                "availabilityStatus": str(item.get("availability_status") or ""),
                "healthBucket": str(item.get("availability_health_bucket") or ""),
                "current": name == current_name,
            }
        )
    if current_name and current_name not in seen:
        entries.insert(
            0,
            {
                "providerName": current_name,
                "configProviderName": current_name,
                "displayName": current_name,
                "defaultModel": str(provider_status.get("provider_model") or ""),
                "plannerKind": str(provider_status.get("provider_planner") or ""),
                "wireApi": str(provider_status.get("provider_tools") or ""),
                "authReady": bool(provider_status.get("provider_auth_ready")),
                "authReason": str(provider_status.get("provider_auth_reason") or ""),
                "statusState": str(provider_status.get("provider_status_state") or ""),
                "statusReason": str(provider_status.get("provider_status_reason") or ""),
                "availabilityStatus": str(provider_status.get("availability_status") or ""),
                "healthBucket": str(provider_status.get("availability_health_bucket") or ""),
                "current": True,
            },
        )
    return entries
