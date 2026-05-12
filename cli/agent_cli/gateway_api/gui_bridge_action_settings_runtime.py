from __future__ import annotations

from typing import Any

from cli.agent_cli.providers.model_routing import STANDARD_DELEGATION_NAMES


def runtime_policy_update_payload(payload: dict[str, Any]) -> dict[str, Any]:
    runtime_policy = payload.get("runtimePolicy")
    runtime_policy_payload = dict(runtime_policy) if isinstance(runtime_policy, dict) else {}
    network_access = None
    if "network_access" in runtime_policy_payload:
        network_access = runtime_policy_payload.get("network_access")
    elif "network_access_enabled" in runtime_policy_payload:
        network_access = runtime_policy_payload.get("network_access_enabled")
    elif "network_access" in payload:
        network_access = payload.get("network_access")
    elif "network_access_enabled" in payload:
        network_access = payload.get("network_access_enabled")
    return {
        "approval_policy": runtime_policy_payload.get("approval_policy")
        or payload.get("approval_policy"),
        "sandbox_mode": runtime_policy_payload.get("sandbox_mode") or payload.get("sandbox_mode"),
        "web_search_mode": runtime_policy_payload.get("web_search_mode")
        or payload.get("web_search_mode"),
        "network_access_enabled": network_access,
    }


def model_selection_update_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": str(payload.get("model") or "").strip() or None,
        "reasoning_effort": str(
            payload.get("reasoningEffort") or payload.get("reasoning_effort") or ""
        ).strip()
        or None,
    }


def delegation_selection_update_payloads(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    delegation_models = payload.get("delegationModels")
    if not isinstance(delegation_models, dict):
        delegation_models = payload.get("delegation_models")
    if not isinstance(delegation_models, dict):
        return {}
    updates: dict[str, dict[str, Any]] = {}
    for role_name in STANDARD_DELEGATION_NAMES:
        role_payload = delegation_models.get(role_name)
        if not isinstance(role_payload, dict):
            continue
        clear = bool(role_payload.get("clear"))
        updates[role_name] = {
            "model": str(role_payload.get("model") or "").strip() or None if not clear else None,
            "provider": (
                str(role_payload.get("provider") or "")
                if "provider" in role_payload and not clear
                else None
            ),
            "reasoning_effort": (
                str(
                    role_payload.get("reasoningEffort")
                    or role_payload.get("reasoning_effort")
                    or ""
                ).strip()
                or None
                if not clear
                else None
            ),
            "timeout": (
                role_payload.get("timeout") if not clear and "timeout" in role_payload else None
            ),
            "clear": clear,
        }
    return updates


def apply_settings_updates(runtime: Any, payload: dict[str, Any]) -> None:
    runtime.configure_runtime_policy(**runtime_policy_update_payload(payload))

    provider = str(payload.get("provider") or payload.get("providerName") or "").strip()
    if provider:
        write_scope = (
            str(payload.get("providerWriteScope") or payload.get("writeScope") or "session").strip()
            or "session"
        )
        runtime.agent.switch_provider(provider, write_scope=write_scope)
        sync_request_user_input = getattr(
            runtime, "_sync_request_user_input_mode_from_provider", None
        )
        if callable(sync_request_user_input):
            sync_request_user_input()

    model_update = model_selection_update_payload(payload)
    if model_update["model"] is not None or model_update["reasoning_effort"] is not None:
        runtime.configure_model_selection(**model_update)

    for role_name, role_update in delegation_selection_update_payloads(payload).items():
        runtime.configure_delegate_selection(role_name, **role_update)

    if "browserHeadless" in payload:
        runtime._gui_browser_headless = bool(payload.get("browserHeadless"))
    if "pluginAutoLoad" in payload:
        runtime._gui_plugin_auto_load = bool(payload.get("pluginAutoLoad"))
