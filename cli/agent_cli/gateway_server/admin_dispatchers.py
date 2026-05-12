from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from cli.agent_cli.gateway_server import admin_dispatchers_runtime
from cli.agent_cli.gateway_server.request_parsing import (
    config_requested_delegation_models as _config_requested_delegation_models,
    config_requested_reasoning_effort as _config_requested_reasoning_effort,
    config_requested_runtime_policy as _config_requested_runtime_policy,
    current_delegation_signature as _current_delegation_signature,
    delegation_requested_reasoning_effort as _delegation_requested_reasoning_effort,
    delegation_settings_snapshot as _delegation_settings_snapshot,
    known_model_tokens as _known_model_tokens,
    normalized_delegation_signature as _normalized_delegation_signature,
)
from cli.agent_cli.providers.model_routing import STANDARD_DELEGATION_NAMES

JsonMap = dict[str, Any]


def config_settings_snapshot(
    runtime: Any,
    *,
    runtime_registry_payload_fn: Callable[[Any], JsonMap],
) -> JsonMap:
    provider_status = dict(runtime.agent.provider_status() or {})
    workspace_root = getattr(runtime, "cwd", None) or Path.cwd()
    runtime_policy = dict(getattr(runtime, "runtime_policy_status", lambda: {})() or {})
    if str(runtime_policy.get("network_access") or "").strip().lower() == "disabled":
        runtime_policy["network_access"] = "restricted"
    runtime_registry = runtime_registry_payload_fn(runtime)
    delegation_models = _delegation_settings_snapshot(runtime)
    return {
        "model": str(provider_status.get("provider_model") or provider_status.get("model_key") or ""),
        "reasoningEffort": str(provider_status.get("provider_reasoning_effort") or ""),
        "delegationModels": delegation_models,
        "delegateOverrideCount": sum(1 for item in delegation_models.values() if bool(item.get("overrideActive"))),
        "browserHeadless": bool(getattr(runtime, "_gui_browser_headless", False)),
        "pluginAutoLoad": bool(getattr(runtime, "_gui_plugin_auto_load", True)),
        "workspaceRoot": str(Path(str(workspace_root)).resolve()),
        "workspaceTrust": str(runtime_registry.get("workspaceTrust") or "trusted"),
        "providerLabel": str(provider_status.get("provider_label") or ""),
        "runtimePolicy": runtime_policy,
        "mcpServers": list(runtime_registry.get("mcpServers") or []),
        "appConnectors": list(runtime_registry.get("appConnectors") or []),
        "runtimeRegistry": runtime_registry,
    }


def config_validation_payload(
    *,
    runtime: Any,
    params: JsonMap,
    runtime_registry_payload_fn: Callable[[Any], JsonMap],
) -> JsonMap:
    current = config_settings_snapshot(runtime, runtime_registry_payload_fn=runtime_registry_payload_fn)
    return admin_dispatchers_runtime.config_validation_payload(
        current=current,
        params=params,
        known_selectors=_known_model_tokens(runtime),
        standard_delegation_names=STANDARD_DELEGATION_NAMES,
        requested_policy=_config_requested_runtime_policy(params),
        requested_reasoning_effort=_config_requested_reasoning_effort(params),
        requested_delegation_models=_config_requested_delegation_models(params),
        normalized_delegation_signature_fn=_normalized_delegation_signature,
        current_delegation_signature_fn=_current_delegation_signature,
        delegation_requested_reasoning_effort_fn=_delegation_requested_reasoning_effort,
    )


def config_apply_result(
    *,
    runtime: Any,
    params: JsonMap,
    runtime_registry_payload_fn: Callable[[Any], JsonMap],
) -> JsonMap:
    validation = config_validation_payload(
        runtime=runtime,
        params=params,
        runtime_registry_payload_fn=runtime_registry_payload_fn,
    )
    return admin_dispatchers_runtime.config_apply_result(
        runtime=runtime,
        params=params,
        validation=validation,
        standard_delegation_names=STANDARD_DELEGATION_NAMES,
        requested_policy=_config_requested_runtime_policy(params),
        requested_reasoning_effort=_config_requested_reasoning_effort(params),
        requested_delegation_models=_config_requested_delegation_models(params),
        delegation_requested_reasoning_effort_fn=_delegation_requested_reasoning_effort,
        config_settings_snapshot_fn=config_settings_snapshot,
        runtime_registry_payload_fn=runtime_registry_payload_fn,
    )


def config_restart_report(
    *,
    runtime: Any,
    params: JsonMap,
    runtime_registry_payload_fn: Callable[[Any], JsonMap],
) -> JsonMap:
    validation = config_validation_payload(
        runtime=runtime,
        params=params,
        runtime_registry_payload_fn=runtime_registry_payload_fn,
    )
    return admin_dispatchers_runtime.config_restart_report(validation=validation)
