from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping

from .auth import is_auth_status_code
from .transports import MCPTransportConfig, MCPTransportConnection, MCPTransportError

MCPConnectionStatus = Literal["pending", "connected", "needs-auth", "failed", "disabled"]
DESCRIPTOR_KINDS = ("tools", "prompts", "resources")
LIST_CHANGED_METHODS: dict[str, str] = {
    "notifications/tools/list_changed": "tools",
    "tools/list_changed": "tools",
    "notifications/prompts/list_changed": "prompts",
    "prompts/list_changed": "prompts",
    "notifications/resources/list_changed": "resources",
    "resources/list_changed": "resources",
}
CHANNEL_MESSAGE_METHODS = {
    "notifications/channel/message",
    "channel/message",
    "notifications/channels/message",
    "channels/message",
}
PERMISSION_REQUEST_METHODS = {
    "notifications/permission/request",
    "permission/request",
    "notifications/permissions/request",
    "permissions/request",
}


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: MCPTransportConfig
    enabled: bool = True
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPConnectionHandle:
    name: str
    fingerprint: str
    connected_at: float
    transport: MCPTransportConnection
    session: Any | None = None
    server_info: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)
    instructions: str = ""

    def close(self) -> None:
        self.transport.close()


@dataclass(frozen=True)
class MCPConnectionResult:
    name: str
    status: MCPConnectionStatus
    error_code: str = ""
    error: str = ""
    handle: MCPConnectionHandle | None = None
    from_cache: bool = False
    retry_attempt: int = 0
    retry_in_sec: float = 0.0


@dataclass
class _RetryState:
    attempt: int = 0
    next_retry_at: float = 0.0


@dataclass
class _DescriptorCache:
    values: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    dirty: set[str] = field(default_factory=lambda: set(DESCRIPTOR_KINDS))


def status_from_transport_error(exc: MCPTransportError) -> MCPConnectionStatus:
    if exc.status_code is not None and is_auth_status_code(exc.status_code):
        return "needs-auth"
    return "failed"


def is_stale_handle(handle: MCPConnectionHandle) -> bool:
    session = handle.session
    if session is None:
        return False
    process = getattr(session, "process", None)
    poll = getattr(process, "poll", None)
    if callable(poll):
        try:
            if poll() is not None:
                return True
        except Exception:
            return True
    closed = getattr(session, "_closed", None)
    if isinstance(closed, bool) and closed:
        return True
    return False


def build_cache_key(config: MCPServerConfig) -> str:
    normalized_name = str(config.name or "").strip()
    auth_headers: list[tuple[str, str]] = []
    auth_token = ""
    if config.transport.auth:
        auth_token = str(config.transport.auth.token or "")
        auth_headers = sorted(
            (str(key), str(value))
            for key, value in dict(config.transport.auth.headers or {}).items()
        )
    payload = {
        "name": normalized_name,
        "enabled": config.enabled,
        "transport": {
            "transport": config.transport.transport,
            "timeout_sec": float(config.transport.timeout_sec),
            "command": list(config.transport.command),
            "args": list(config.transport.args),
            "env": {str(k): str(v) for k, v in sorted(config.transport.env.items())},
            "url": config.transport.url,
            "headers": {str(k): str(v) for k, v in sorted(config.transport.headers.items())},
            "auth_token": auth_token,
            "auth_headers": auth_headers,
            "enabled": config.transport.enabled,
        },
        "metadata": {str(k): str(v) for k, v in sorted(config.metadata.items())},
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{normalized_name}|{digest}"


def notification_method(notification: Any) -> str:
    if isinstance(notification, Mapping):
        return str(notification.get("method") or "").strip()
    return str(notification or "").strip()


def notification_payload(notification: Any) -> dict[str, Any]:
    if isinstance(notification, Mapping):
        payload = dict(notification)
        params = payload.get("params")
        if isinstance(params, Mapping):
            payload["params"] = dict(params)
        return payload
    return {"method": str(notification or "").strip()}


def is_channel_message_method(method: str) -> bool:
    normalized = str(method or "").strip().lower()
    if normalized in CHANNEL_MESSAGE_METHODS:
        return True
    parts = [part for part in normalized.split("/") if part]
    return len(parts) >= 2 and parts[-1] == "message" and ("channel" in parts or "channels" in parts)


def is_permission_request_method(method: str) -> bool:
    normalized = str(method or "").strip().lower()
    if normalized in PERMISSION_REQUEST_METHODS:
        return True
    parts = [part for part in normalized.split("/") if part]
    return len(parts) >= 2 and parts[-1] == "request" and ("permission" in parts or "permissions" in parts)


def consume_list_changed_notifications(
    *,
    server_name: str,
    session: Any,
    channel_message_cache: dict[str, list[dict[str, Any]]],
    permission_request_cache: dict[str, list[dict[str, Any]]],
    invalidate_remote_descriptors: Callable[..., None],
    resolve_method: Callable[[Any], str],
    resolve_payload: Callable[[Any], dict[str, Any]],
    is_channel_message: Callable[[str], bool],
    is_permission_request: Callable[[str], bool],
) -> None:
    drain = getattr(session, "drain_notifications", None)
    if not callable(drain):
        return
    try:
        notifications = list(drain() or [])
    except Exception:
        return
    dirty_kinds: set[str] = set()
    for notification in notifications:
        method = resolve_method(notification)
        kind = LIST_CHANGED_METHODS.get(method)
        if kind:
            dirty_kinds.add(kind)
        payload = resolve_payload(notification)
        if is_channel_message(method):
            channel_message_cache.setdefault(server_name, []).append(payload)
        elif is_permission_request(method):
            permission_request_cache.setdefault(server_name, []).append(payload)
    if dirty_kinds:
        invalidate_remote_descriptors(name=server_name, kinds=dirty_kinds)


def remote_descriptors(
    *,
    name: str,
    session: Any,
    kind: str,
    method_name: str,
    descriptor_cache: dict[str, _DescriptorCache],
    consume_list_changed: Callable[[str, Any], None],
) -> list[dict[str, Any]]:
    server_name = str(name or "").strip()
    if not server_name or kind not in DESCRIPTOR_KINDS:
        return []
    consume_list_changed(server_name, session)
    cache = descriptor_cache.setdefault(server_name, _DescriptorCache())
    cached = cache.values.get(kind)
    if kind not in cache.dirty and isinstance(cached, list):
        return [dict(item) for item in cached]
    list_method = getattr(session, method_name, None)
    if not callable(list_method):
        cache.dirty.discard(kind)
        cache.values[kind] = []
        return []
    try:
        raw = list_method()
    except Exception:
        return [dict(item) for item in cached] if isinstance(cached, list) else []
    parsed = [dict(item) for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []
    cache.values[kind] = parsed
    cache.dirty.discard(kind)
    return [dict(item) for item in parsed]


def drain_notification_cache(
    *,
    name: str,
    cache: dict[str, list[dict[str, Any]]],
    get_cached_connection_by_name: Callable[[str], MCPConnectionHandle | None],
    consume_list_changed: Callable[[str, Any], None],
    resolve_payload: Callable[[Any], dict[str, Any]],
) -> list[dict[str, Any]]:
    server_name = str(name or "").strip()
    if not server_name:
        return []
    handle = get_cached_connection_by_name(server_name)
    if handle is not None:
        consume_list_changed(server_name, handle.session)
    pending = cache.get(server_name)
    if not isinstance(pending, list) or not pending:
        return []
    drained = [resolve_payload(item) for item in pending]
    cache[server_name] = []
    return drained


def notification_server_names(
    *,
    server_name: str | None,
    handles: Mapping[str, MCPConnectionHandle],
    channel_message_cache: dict[str, list[dict[str, Any]]],
    permission_request_cache: dict[str, list[dict[str, Any]]],
) -> list[str]:
    normalized = str(server_name or "").strip()
    if normalized:
        return [normalized]
    names: set[str] = set()
    for handle in handles.values():
        name = str(handle.name or "").strip()
        if name:
            names.add(name)
    names.update(str(name).strip() for name in channel_message_cache if str(name).strip())
    names.update(str(name).strip() for name in permission_request_cache if str(name).strip())
    return sorted(names)
