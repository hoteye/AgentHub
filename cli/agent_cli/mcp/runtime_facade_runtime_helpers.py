from __future__ import annotations

from typing import Any, Mapping

from .config import effective_mcp_configs
from .models import McpRuntimeSnapshot
from .remote_descriptors import read_remote_resource
from .resource_projection import read_projected_mcp_resource
from .runtime_support import collect_runtime_sources, resolved_servers_from_entries
from .runtime_facade_helpers import (
    build_server_entries,
    build_snapshot,
    payload_from_entries,
)


def list_channel_messages(facade: Any, *, server_name: str | None = None) -> list[dict[str, Any]]:
    if not facade._gate_enabled("mcp_channel_notifications_enabled"):
        return []
    _, _, _, entries = facade._refresh_state()
    server_names = facade._selected_server_names(entries=entries, server_name=server_name)
    if not server_names:
        return []
    list_fn = facade._resolve_client_callable(("drain_channel_messages", "list_channel_messages"))
    if not callable(list_fn):
        raise RuntimeError("mcp channel notifications relay is unavailable")
    rows: list[dict[str, Any]] = []
    for name in server_names:
        raw = facade._call_client_list_fn(list_fn, name)
        if not isinstance(raw, list):
            continue
        for item in raw:
            row = facade._normalize_notification_row(item, server_name=name)
            if row:
                rows.append(row)
    return rows


def list_permission_requests(facade: Any, *, server_name: str | None = None) -> list[dict[str, Any]]:
    if not facade._gate_enabled("mcp_permission_relay_enabled"):
        return []
    _, _, _, entries = facade._refresh_state()
    server_names = facade._selected_server_names(entries=entries, server_name=server_name)
    if not server_names:
        return []
    list_fn = facade._resolve_client_callable(("drain_permission_requests", "list_permission_requests"))
    if not callable(list_fn):
        raise RuntimeError("mcp permission relay is unavailable")
    rows: list[dict[str, Any]] = []
    for name in server_names:
        raw = facade._call_client_list_fn(list_fn, name)
        if not isinstance(raw, list):
            continue
        for item in raw:
            row = facade._normalize_notification_row(item, server_name=name)
            if row is None:
                continue
            request_id = str(
                row.get("request_id") or row.get("requestId") or row.get("id") or ""
            ).strip()
            if request_id:
                row.setdefault("request_id", request_id)
            rows.append(row)
    return rows


def respond_permission_request(
    facade: Any,
    *,
    server_name: str,
    request_id: str,
    approved: bool,
    reason: str = "",
) -> dict[str, Any]:
    if not facade._gate_enabled("mcp_permission_relay_enabled"):
        raise RuntimeError("mcp permission relay is disabled by runtime policy")
    normalized_server = facade._normalize_required_server_name(server_name)
    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        raise ValueError("request_id is required")
    facade._refresh_state()
    respond_fn = facade._resolve_client_callable(
        ("respond_permission_request", "respond_permission", "permission_respond", "respond_to_permission")
    )
    if not callable(respond_fn):
        raise RuntimeError("mcp permission relay is unavailable")
    response = facade._call_client_respond_fn(
        respond_fn,
        server_name=normalized_server,
        request_id=normalized_request_id,
        approved=approved,
        reason=str(reason or ""),
    )
    payload = dict(response) if isinstance(response, Mapping) else {"ok": bool(response)}
    payload.setdefault("server", normalized_server)
    payload.setdefault("request_id", normalized_request_id)
    payload.setdefault("approved", bool(approved))
    payload.setdefault("status", "ok" if bool(payload.get("ok", True)) else "failed")
    return payload


def read_resource(facade: Any, *, server_name: str, uri: str) -> dict[str, Any]:
    payload, _, _, _ = facade._refresh_state()
    handle = facade._client.get_cached_connection_by_name(str(server_name or "").strip())
    if handle is not None:
        remote_payload = read_remote_resource(
            session=getattr(handle, "session", None),
            server_name=str(server_name or "").strip(),
            uri=uri,
        )
        if isinstance(remote_payload, dict) and bool(remote_payload.get("ok")):
            return remote_payload
    return read_projected_mcp_resource(payload, server_name=server_name, uri=uri)


def refresh_state(facade: Any) -> tuple[dict[str, Any], McpRuntimeSnapshot, list[dict[str, Any]], list[dict[str, Any]]]:
    manager = facade._plugin_manager_getter()
    sources = collect_runtime_sources(manager, facade._runtime_dynamic)
    policy = facade._policy_payload()
    result = effective_mcp_configs(
        user=sources["user"],
        workspace=sources["workspace"],
        plugin=sources["plugin"],
        runtime_dynamic=sources["runtime_dynamic"],
        enabled_state=facade._enabled_state,
        policy=policy,
    )
    blocked = [dict(item) for item in list(result.get("blocked") or []) if isinstance(item, Mapping)]
    resolved = resolved_servers_from_entries(result)
    facade._client.prune_stale_servers({item.name for item in resolved})
    connection_results = facade._connection_results(resolved)
    snapshot = build_snapshot(resolved, connection_results, facade._client)
    entries = build_server_entries(resolved, connection_results, snapshot, facade._client)
    payload = payload_from_entries(entries, snapshot)
    return payload, snapshot, blocked, entries
