from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from cli.agent_cli.gateway_protocol.auth_context import GatewayAuthContext
from cli.agent_cli.gateway_protocol.errors import ErrorCodes, GatewayProtocolError
from cli.agent_cli.gateway_server.access_posture_contract import build_access_posture_summary
from cli.agent_cli.gateway_server import dispatcher_direct_handlers
from cli.agent_cli.gateway_server import dispatcher_helpers as dispatcher_helpers_service
from cli.agent_cli.gateway_server import dispatcher_runtime
from cli.agent_cli.gateway_server.authz import require_gateway_authorized
from cli.agent_cli.gateway_server.method_registry import GatewayServerMethodRegistry
from cli.agent_cli.gateway_server.methods import merge_handler_maps
from cli.agent_cli.gateway_server.methods.access import ACCESS_FAMILY
from cli.agent_cli.gateway_server.methods.approvals import APPROVALS_FAMILY
from cli.agent_cli.gateway_server.methods.browser import BROWSER_FAMILY
from cli.agent_cli.gateway_server.methods.config import CONFIG_FAMILY
from cli.agent_cli.gateway_server.methods.connect import CONNECT_FAMILY
from cli.agent_cli.gateway_server.methods.gateway_state import GATEWAY_STATE_FAMILY
from cli.agent_cli.gateway_server.methods.github import GITHUB_FAMILY
from cli.agent_cli.gateway_server.methods.health import HEALTH_FAMILY
from cli.agent_cli.gateway_server.methods.logs import LOGS_FAMILY
from cli.agent_cli.gateway_server.methods.nodes import NODES_FAMILY
from cli.agent_cli.gateway_server.methods.plugins import PLUGINS_FAMILY
from cli.agent_cli.gateway_server.methods.workflows import WORKFLOWS_FAMILY
from cli.agent_cli.gateway_server.request_parsing import (
    build_gateway_request_scope as _build_gateway_request_scope,
    resolve_gateway_auth_context as _resolve_gateway_auth_context,
)
from cli.agent_cli.gateway_server.response_builders import (
    gateway_item_to_dict as _gateway_item_to_dict,
    nodes_last_seen_at as _nodes_last_seen_at,
    pairing_pending_refs as _pairing_pending_refs,
)
from cli.agent_cli.gateway_server.request_scope import with_gateway_request_scope
from cli.agent_cli.gateway_server.write_budget import consume_control_plane_write_budget
from shared.web_automation.proxy import run_browser_proxy_command

JsonMap = dict[str, Any]

gateway_method_families = (
    CONNECT_FAMILY,
    CONFIG_FAMILY,
    ACCESS_FAMILY,
    NODES_FAMILY,
    HEALTH_FAMILY,
    GATEWAY_STATE_FAMILY,
    APPROVALS_FAMILY,
    BROWSER_FAMILY,
    GITHUB_FAMILY,
    PLUGINS_FAMILY,
    WORKFLOWS_FAMILY,
    LOGS_FAMILY,
)
gateway_method_handlers = merge_handler_maps(gateway_method_families)
_METHOD_REGISTRY = GatewayServerMethodRegistry(handlers=gateway_method_handlers)
_LEGACY_METHOD_ALIASES: dict[str, str] = {
    "gateway/state": "gateway.state.get",
    "approval/list": "approvals.list",
    "approval/decide": "approvals.resolve",
    "browser/proxy": "browser.proxy",
}
_LEGACY_ONLY_METHODS = {
    "gateway/dispatch",
    "gateway/webhook",
}


@dataclass(slots=True, frozen=True)
class GatewayDispatchResult:
    ok: bool
    result: JsonMap | None = None
    error_code: int | None = None
    error_message: str | None = None
    error_data: JsonMap = field(default_factory=dict)
    transport_context: JsonMap = field(default_factory=dict)


def gateway_dispatcher_methods() -> tuple[str, ...]:
    return dispatcher_runtime.gateway_dispatcher_methods(
        legacy_only_methods=_LEGACY_ONLY_METHODS,
        legacy_method_aliases=_LEGACY_METHOD_ALIASES,
        method_registry=_METHOD_REGISTRY,
        gateway_method_handlers=gateway_method_handlers,
    )


def gateway_dispatcher_supports_method(method: str) -> bool:
    return dispatcher_runtime.gateway_dispatcher_supports_method(
        method,
        gateway_dispatcher_methods_fn=gateway_dispatcher_methods,
    )


def dispatch_gateway_method(
    *,
    method: str,
    params: JsonMap,
    runtime: Any,
    action_worker: Any | None = None,
    request_id: Any = None,
    client_info: JsonMap | None = None,
) -> GatewayDispatchResult:
    return dispatcher_runtime.dispatch_gateway_method(
        method=method,
        params=params,
        runtime=runtime,
        action_worker=action_worker,
        request_id=request_id,
        client_info=client_info,
        legacy_method_aliases=_LEGACY_METHOD_ALIASES,
        method_registry=_METHOD_REGISTRY,
        resolve_gateway_auth_context_fn=_resolve_gateway_auth_context,
        require_gateway_authorized_fn=require_gateway_authorized,
        consume_control_plane_write_budget_fn=consume_control_plane_write_budget,
        gateway_protocol_error_type=GatewayProtocolError,
        error_codes=ErrorCodes,
        protocol_error_failure_fn=_protocol_error_failure,
        build_gateway_request_scope_fn=_build_gateway_request_scope,
        direct_method_handlers=_DIRECT_METHOD_HANDLERS,
        run_browser_proxy_command=run_browser_proxy_command,
        dispatcher_direct_handlers_module=dispatcher_direct_handlers,
        with_gateway_request_scope_fn=with_gateway_request_scope,
        gateway_method_handlers=gateway_method_handlers,
        success_fn=_success,
        failure_fn=_failure,
    )









def _capabilities_payload(*, runtime: Any, auth: GatewayAuthContext | None = None) -> JsonMap:
    provider_status = dict(runtime.agent.provider_status() or {})
    runtime_registry = _runtime_registry_payload(runtime)
    access_posture = build_access_posture_summary(runtime, auth=auth)
    return {
        "platformFamily": provider_status.get("platform_family") or "-",
        "platformOs": provider_status.get("platform_os") or "-",
        "shellKind": provider_status.get("shell_kind") or "-",
        "providerLabel": provider_status.get("provider_label") or "-",
        "runtimeRegistry": runtime_registry,
        "accessPosture": access_posture,
        "methods": [item.metadata.to_dict() for item in _METHOD_REGISTRY.list()],
        "legacyMethods": sorted(_LEGACY_ONLY_METHODS | set(_LEGACY_METHOD_ALIASES)),
    }


def _runtime_registry_payload(runtime: Any) -> JsonMap:
    return dispatcher_helpers_service.runtime_registry_payload(runtime)


def _nodes_inventory_payload(
    *,
    snapshot: JsonMap,
    access_posture: JsonMap,
    runtime_registry: JsonMap,
    limit: int,
) -> JsonMap:
    events = [_gateway_item_to_dict(item) for item in list(snapshot.get("events") or [])]
    workflow_runs = [_gateway_item_to_dict(item) for item in list(snapshot.get("workflow_runs") or [])]
    approval_tickets = [_gateway_item_to_dict(item) for item in list(snapshot.get("approval_tickets") or [])]

    access = dict(access_posture.get("access") or {})
    local_access = dict(access.get("local") or {})
    remote_access = dict(access.get("remote") or {})
    auth = dict(access_posture.get("auth") or {})
    pairing = dict(access_posture.get("pairing") or {})
    pairing_count = int(pairing.get("pendingRequestCount") or 0)
    pending_approval_count = int(pairing.get("pendingApprovalCount") or 0)
    pending_refs = _pairing_pending_refs(pairing)
    last_seen_at = _nodes_last_seen_at(events)
    runtime_view = {
        "workspaceTrust": str(runtime_registry.get("workspaceTrust") or "unknown"),
        "toolCount": int(runtime_registry.get("toolCount") or 0),
        "mcpServerCount": len(list(runtime_registry.get("mcpServers") or [])),
        "appConnectorCount": len(list(runtime_registry.get("appConnectors") or [])),
    }
    activity = {
        "eventCount": len(events),
        "workflowCount": len(workflow_runs),
        "approvalCount": len(approval_tickets),
        "lastSeenAt": last_seen_at,
    }
    pairing_view = {
        "pendingRequestCount": pairing_count,
        "pendingApprovalCount": pending_approval_count,
        "pendingRefs": pending_refs,
        "source": str(pairing.get("source") or "unknown"),
        "hasNativeContract": bool(pairing.get("hasNativeContract")),
        "writeSupported": False,
    }

    nodes: list[JsonMap] = []
    local_enabled = bool(local_access.get("enabled"))
    nodes.append(
        {
            "nodeId": "node.local.app_server",
            "deviceId": "local-app-server",
            "kind": "local",
            "label": "Local App Server",
            "status": "online" if local_enabled else "offline",
            "access": {
                "enabled": local_enabled,
                "channel": local_access.get("channel"),
                "origin": local_access.get("origin"),
                "posture": access.get("posture"),
            },
            "auth": dict(auth),
            "pairing": dict(pairing_view),
            "activity": dict(activity),
            "runtime": dict(runtime_view),
        }
    )

    remote_enabled = bool(remote_access.get("enabled"))
    if remote_enabled or pairing_count > 0:
        nodes.append(
            {
                "nodeId": "node.remote.gateway",
                "deviceId": str(auth.get("actorId") or "remote-gateway"),
                "kind": "remote",
                "label": "Remote Gateway Client",
                "status": "online" if remote_enabled else "pending_pairing",
                "access": {
                    "enabled": remote_enabled,
                    "channel": remote_access.get("channel"),
                    "origin": remote_access.get("origin"),
                    "posture": access.get("posture"),
                },
                "auth": dict(auth),
                "pairing": dict(pairing_view),
                "activity": dict(activity),
                "runtime": dict(runtime_view),
            }
        )

    devices = [
        {
            "deviceId": str(item.get("deviceId") or item.get("nodeId") or ""),
            "nodeId": str(item.get("nodeId") or ""),
            "kind": str(item.get("kind") or "unknown"),
            "status": str(item.get("status") or "unknown"),
            "label": str(item.get("label") or ""),
        }
        for item in nodes
    ]
    return {
        "nodes": nodes,
        "devices": devices,
        "summary": {
            "totalNodes": len(nodes),
            "localNodes": sum(1 for item in nodes if str(item.get("kind") or "") == "local"),
            "remoteNodes": sum(1 for item in nodes if str(item.get("kind") or "") == "remote"),
            "pendingPairingRequestCount": pairing_count,
            "pendingApprovalCount": pending_approval_count,
            "recentEvents": len(events),
            "recentWorkflowRuns": len(workflow_runs),
            "recentApprovalTickets": len(approval_tickets),
            "mcpServerCount": runtime_view["mcpServerCount"],
            "appConnectorCount": runtime_view["appConnectorCount"],
            "lastSeenAt": last_seen_at,
            "limit": int(limit),
        },
        "accessPosture": access_posture,
        "runtimeRegistry": runtime_registry,
        "capabilities": {
            "readOnly": True,
            "pairingWriteSupported": False,
            "pairingWriteReason": "nodes.list only provides read-only inventory; pairing decisions stay in approval flows.",
        },
        "source": {
            "contract": "nodes.list.v1",
            "derivedFrom": ["access.posture.get", "runtimeRegistry", "gateway_state_snapshot"],
        },
    }


def _success(result: JsonMap) -> GatewayDispatchResult:
    return GatewayDispatchResult(ok=True, result=dict(result or {}))


def _failure(code: int, message: str, *, detail: str) -> GatewayDispatchResult:
    return GatewayDispatchResult(
        ok=False,
        error_code=int(code),
        error_message=str(message),
        error_data={"detail": str(detail)},
    )


def _protocol_error_failure(error: GatewayProtocolError) -> GatewayDispatchResult:
    return dispatcher_runtime.protocol_error_failure(
        error,
        error_codes=ErrorCodes,
        result_type=GatewayDispatchResult,
    )


def _available_log_sources(runtime: Any) -> dict[str, dict[str, Any]]:
    return dispatcher_helpers_service.available_log_sources(runtime)


def _tail_text_lines(path: Path, *, limit: int) -> tuple[list[str], bool]:
    return dispatcher_helpers_service.tail_text_lines(path, limit=limit)


_DIRECT_METHOD_HANDLERS: dict[str, Callable[..., GatewayDispatchResult]] = (
    dispatcher_direct_handlers._DIRECT_METHOD_HANDLERS
)
