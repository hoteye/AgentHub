from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.gateway_api import (
    gui_bridge_action_helpers_runtime as gui_bridge_action_helpers_runtime_service,
)
from cli.agent_cli.gateway_api import (
    gui_bridge_action_mapping_runtime as gui_bridge_action_mapping_runtime_service,
)
from cli.agent_cli.gateway_api import (
    gui_bridge_action_settings_runtime as gui_bridge_action_settings_runtime_service,
)
from cli.agent_cli.gateway_api import gui_bridge_payloads as gui_bridge_payloads_service

GuiBridgeResponseBuilder = Callable[..., dict[str, Any]]


def gateway_dispatch(
    runtime,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    dispatch_gateway_method_fn: Callable[..., Any],
    success: GuiBridgeResponseBuilder,
    error: GuiBridgeResponseBuilder,
) -> dict[str, Any]:
    canonical_payload = gui_bridge_action_mapping_runtime_service.normalize_gateway_action_payload(
        action,
        payload,
    )
    result = dispatch_gateway_method_fn(
        method=action,
        params=canonical_payload,
        runtime=runtime,
        request_id=request_id,
        client_info={"name": "gui_http_server", "clientType": "gui"},
    )
    if not result.ok:
        detail = gui_bridge_action_mapping_runtime_service.gateway_error_detail(result)
        return error(
            request_id=request_id,
            action=action,
            code=f"{action}.failed",
            message=str(result.error_message or "gateway dispatch failed"),
            detail=detail,
            retryable=bool((result.error_data or {}).get("retryable")),
        )
    return success(
        request_id=request_id,
        action=action,
        data=result.result or {},
    )


def audit_list(
    runtime,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    success: GuiBridgeResponseBuilder,
) -> dict[str, Any]:
    limit = gui_bridge_action_mapping_runtime_service.payload_limit(payload, default=50)
    trace_id = gui_bridge_action_mapping_runtime_service.payload_trace_id(payload)
    snapshot = runtime.gateway_state_snapshot(limit=limit)
    return success(
        request_id=request_id,
        action=action,
        data=gui_bridge_action_mapping_runtime_service.audit_records_payload(
            snapshot, trace_id=trace_id
        ),
    )


def plugin_list(
    runtime, *, request_id: str, action: str, success: GuiBridgeResponseBuilder
) -> dict[str, Any]:
    event = runtime.tools.list_plugins()
    return success(
        request_id=request_id,
        action=action,
        data=gui_bridge_action_mapping_runtime_service.plugin_list_payload(
            list(event.payload.get("plugins") or []),
            normalize_plugin_summary_fn=gui_bridge_payloads_service.normalize_plugin_summary,
        ),
    )


def connector_list(
    runtime,
    *,
    request_id: str,
    action: str,
    dispatch_gateway_method_fn: Callable[..., Any],
    success: GuiBridgeResponseBuilder,
) -> dict[str, Any]:
    return gui_bridge_action_helpers_runtime_service.connector_list_impl(
        runtime=runtime,
        request_id=request_id,
        action=action,
        dispatch_gateway_method_fn=dispatch_gateway_method_fn,
        success=success,
        connector_routed_payload_fn=gui_bridge_action_mapping_runtime_service.connector_routed_payload,
        gui_runtime_policy_status_fn=gui_bridge_payloads_service.gui_runtime_policy_status,
        normalize_plugin_summary_fn=gui_bridge_payloads_service.normalize_plugin_summary,
        plugin_state_map_fn=gui_bridge_action_mapping_runtime_service.plugin_state_map,
        connector_fallback_payload_fn=gui_bridge_action_mapping_runtime_service.connector_fallback_payload,
        plugin_manager_app_connector_entries_fn=gui_bridge_payloads_service.plugin_manager_app_connector_entries,
    )


def settings_get(
    runtime, *, request_id: str, action: str, success: GuiBridgeResponseBuilder
) -> dict[str, Any]:
    return success(
        request_id=request_id,
        action=action,
        data=gui_bridge_payloads_service.settings_snapshot(runtime),
    )


def plugin_mutation(
    runtime,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    operation: str,
    success: GuiBridgeResponseBuilder,
    error: GuiBridgeResponseBuilder,
) -> dict[str, Any]:
    return gui_bridge_action_helpers_runtime_service.plugin_mutation_impl(
        runtime=runtime,
        request_id=request_id,
        action=action,
        payload=payload,
        operation=operation,
        success=success,
        error=error,
        normalize_plugin_summary_fn=gui_bridge_payloads_service.normalize_plugin_summary,
        plugin_mutation_result_payload_fn=gui_bridge_action_mapping_runtime_service.plugin_mutation_result_payload,
    )


def settings_update(
    runtime,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    success: GuiBridgeResponseBuilder,
) -> dict[str, Any]:
    gui_bridge_action_settings_runtime_service.apply_settings_updates(runtime, payload)
    return success(
        request_id=request_id,
        action=action,
        data=gui_bridge_payloads_service.settings_snapshot(runtime),
    )
