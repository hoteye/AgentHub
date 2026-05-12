from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.tools_core.registry import app_connector_contract_item, gateway_connector_contract_item


GuiBridgeResponseBuilder = Callable[..., Dict[str, Any]]


def connector_list_impl(
    *,
    runtime: Any,
    request_id: str,
    action: str,
    dispatch_gateway_method_fn: Callable[..., Any],
    success: GuiBridgeResponseBuilder,
    connector_routed_payload_fn: Callable[..., Dict[str, Any]],
    gui_runtime_policy_status_fn: Callable[[Any], Dict[str, Any]],
    normalize_plugin_summary_fn: Callable[[Any], Dict[str, Any]],
    plugin_state_map_fn: Callable[[list[Dict[str, Any]]], Dict[str, Any]],
    connector_fallback_payload_fn: Callable[..., Dict[str, Any]],
    plugin_manager_app_connector_entries_fn: Callable[[Any], list[Dict[str, Any]]],
) -> Dict[str, Any]:
    routed = dispatch_gateway_method_fn(
        method="plugins.connectors.list",
        params={},
        runtime=runtime,
        request_id=request_id,
        client_info={"name": "gui_http_server", "clientType": "gui"},
    )
    if routed.ok:
        routed_payload = dict(routed.result or {})
        return success(
            request_id=request_id,
            action=action,
            data=connector_routed_payload_fn(
                routed_payload,
                runtime_policy_status=gui_runtime_policy_status_fn(runtime),
            ),
        )

    registry = runtime.gateway_registry()
    approval_policy = str(runtime.runtime_policy_status().get("approval_policy") or "").strip().lower()
    plugin_manager = getattr(runtime.tools, "_plugin_manager", None)
    normalized_plugins = [
        normalize_plugin_summary_fn(entry)
        for entry in runtime.tools.list_plugins().payload.get("plugins") or []
    ]
    plugin_state = plugin_state_map_fn(normalized_plugins)
    return success(
        request_id=request_id,
        action=action,
        data=connector_fallback_payload_fn(
            registry=registry,
            approval_policy=approval_policy,
            plugin_state=plugin_state,
            plugin_manager_entries=plugin_manager_app_connector_entries_fn(plugin_manager),
            gateway_connector_contract_item_fn=gateway_connector_contract_item,
            app_connector_contract_item_fn=app_connector_contract_item,
        ),
    )


def plugin_mutation_impl(
    *,
    runtime: Any,
    request_id: str,
    action: str,
    payload: Dict[str, Any],
    operation: str,
    success: GuiBridgeResponseBuilder,
    error: GuiBridgeResponseBuilder,
    normalize_plugin_summary_fn: Callable[[Any], Dict[str, Any]],
    plugin_mutation_result_payload_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    plugin_name = str(payload.get("plugin_id") or payload.get("plugin_name") or "").strip()
    if operation in {"enable", "disable"} and not plugin_name:
        return error(
            request_id=request_id,
            action=action,
            code=f"{action}.invalid_payload",
            message="plugin_id is required",
        )
    if operation == "enable":
        event = runtime.tools.enable_plugin(plugin_name)
    elif operation == "disable":
        event = runtime.tools.disable_plugin(plugin_name)
    else:
        event = runtime.tools.reload_plugins()
    payload_map = dict(event.payload or {})
    plugins = [
        normalize_plugin_summary_fn(item)
        for item in list(payload_map.get("plugins") or [])
    ]
    if not event.ok:
        return error(
            request_id=request_id,
            action=action,
            code=f"{action}.failed",
            message=str(payload_map.get("reason") or f"failed to {operation} plugin"),
            detail=payload_map,
        )
    return success(
        request_id=request_id,
        action=action,
        data=plugin_mutation_result_payload_fn(
            payload_map=payload_map,
            plugins=plugins,
            plugin_name=plugin_name,
            operation=operation,
        ),
    )
