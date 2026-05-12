from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from cli.agent_cli.gateway_protocol.auth_context import GatewayAuthContext
from cli.agent_cli.gateway_server.access_posture_contract import build_access_posture_summary
from cli.agent_cli.gateway_server.response_builders import (
    gateway_item_to_dict as _gateway_item_to_dict,
    nodes_last_seen_at as _nodes_last_seen_at,
    pairing_pending_refs as _pairing_pending_refs,
)
from cli.agent_cli.tools_core.registry import runtime_registry_app_connector_entries, runtime_registry_mcp_server_entries

JsonMap = dict[str, Any]


def capabilities_payload(
    *,
    runtime: Any,
    auth: GatewayAuthContext | None = None,
    method_entries: list[JsonMap],
    legacy_methods: list[str],
) -> JsonMap:
    provider_status = dict(runtime.agent.provider_status() or {})
    runtime_registry = runtime_registry_payload(runtime)
    access_posture = build_access_posture_summary(runtime, auth=auth)
    return {
        "platformFamily": provider_status.get("platform_family") or "-",
        "platformOs": provider_status.get("platform_os") or "-",
        "shellKind": provider_status.get("shell_kind") or "-",
        "providerLabel": provider_status.get("provider_label") or "-",
        "runtimeRegistry": runtime_registry,
        "accessPosture": access_posture,
        "methods": list(method_entries),
        "legacyMethods": list(legacy_methods),
    }


def runtime_registry_payload(runtime: Any) -> JsonMap:
    tools = getattr(runtime, "tools", None)
    getter = getattr(tools, "capabilities", None)
    payload = getter() if callable(getter) else {}
    capabilities = dict(payload) if isinstance(payload, dict) else {}
    plugin_manager = getattr(tools, "_plugin_manager", None)
    mcp_servers = runtime_registry_mcp_server_entries(
        plugin_manager,
        runtime_capabilities=capabilities,
    )
    app_connectors = runtime_registry_app_connector_entries(
        plugin_manager,
        runtime_capabilities=capabilities,
    )
    return {
        "workspaceTrust": str(capabilities.get("workspace_trust") or "trusted"),
        "mcpServers": list(mcp_servers),
        "appConnectors": list(app_connectors),
        "toolCount": int(capabilities.get("count") or 0),
        "source": "tools.capabilities" if bool(capabilities) else "runtime",
    }


def nodes_inventory_payload(
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


def available_log_sources(runtime: Any) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    gateway_state_store = getattr(runtime, "gateway_state_store", None)
    base_dir = getattr(gateway_state_store, "base_dir", None)
    if base_dir:
        gateway_root = Path(base_dir)
        for key, filename, label in (
            ("gateway.events", "events.jsonl", "Gateway Events"),
            ("gateway.workflow_runs", "workflow_runs.jsonl", "Gateway Workflow Runs"),
            ("gateway.action_requests", "action_requests.jsonl", "Gateway Action Requests"),
            ("gateway.approval_tickets", "approval_tickets.jsonl", "Gateway Approval Tickets"),
            ("gateway.audit_records", "audit_records.jsonl", "Gateway Audit Records"),
        ):
            candidate = gateway_root / filename
            if candidate.exists():
                sources[key] = {"label": label, "path": candidate}
    thread_store = getattr(runtime, "thread_store", None)
    if thread_store is not None:
        active_thread_id = getattr(thread_store, "get_active_thread_id", None)
        get_thread = getattr(thread_store, "get_thread", None)
        thread_id = active_thread_id() if callable(active_thread_id) else None
        record = get_thread(thread_id) if callable(get_thread) and thread_id else None
        rollout_path = Path(str((record or {}).get("rollout_path") or "")).expanduser() if record else None
        if rollout_path and rollout_path.exists():
            sources["thread.active_rollout"] = {"label": "Active Thread Rollout", "path": rollout_path}
    return sources


def tail_text_lines(path: Path, *, limit: int) -> tuple[list[str], bool]:
    recent: deque[str] = deque(maxlen=max(1, int(limit)))
    total = 0
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            total += 1
            recent.append(raw_line.rstrip("\n"))
    return list(recent), total > len(recent)
