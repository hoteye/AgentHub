from __future__ import annotations

from typing import Any, Callable, Mapping


def runtime_policy_value(runtime_policy: Any, key: str, default: Any = None) -> Any:
    if runtime_policy is None:
        return default
    if isinstance(runtime_policy, Mapping):
        return runtime_policy.get(key, default)
    return getattr(runtime_policy, key, default)


def gate_enabled(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    normalized = str(raw or "").strip().lower()
    return normalized in {"1", "true", "yes", "on", "enabled"}


def build_policy_payload(
    runtime_policy_value_fn: Callable[[str, Any], Any],
    gate_enabled_fn: Callable[[str], bool],
) -> dict[str, Any]:
    def _read_list(key: str) -> list[str] | None:
        raw = runtime_policy_value_fn(key, None)
        if not isinstance(raw, (list, tuple, set)):
            return None
        values = [str(item).strip() for item in raw if str(item).strip()]
        return values or None

    payload: dict[str, Any] = {}
    for key in ("allow_sources", "deny_sources", "allow_names", "deny_names"):
        values = _read_list(key)
        if values is not None:
            payload[key] = values

    require_enabled = runtime_policy_value_fn("require_enabled", None)
    payload["require_enabled"] = bool(require_enabled) if require_enabled is not None else True

    network_access = str(runtime_policy_value_fn("network_access_enabled", "") or "").strip().lower()
    if network_access == "disabled" and "allow_sources" not in payload:
        payload["allow_sources"] = ["plugin", "user", "workspace", "runtime_dynamic"]
    payload["mcp_channel_notifications_enabled"] = gate_enabled_fn("mcp_channel_notifications_enabled")
    payload["mcp_permission_relay_enabled"] = gate_enabled_fn("mcp_permission_relay_enabled")
    return payload


def resolve_client_callable(client: Any, names: tuple[str, ...]) -> Callable[..., Any] | None:
    for name in names:
        candidate = getattr(client, name, None)
        if callable(candidate):
            return candidate
    return None


def call_client_list_fn(fn: Callable[..., Any], server_name: str) -> Any:
    try:
        return fn(name=server_name)
    except TypeError:
        pass
    try:
        return fn(server_name=server_name)
    except TypeError:
        return fn(server_name)


def call_client_respond_fn(
    fn: Callable[..., Any],
    *,
    server_name: str,
    request_id: str,
    approved: bool,
    reason: str,
) -> Any:
    try:
        return fn(
            server_name=server_name,
            request_id=request_id,
            approved=bool(approved),
            reason=reason,
        )
    except TypeError:
        return fn(server_name, request_id, bool(approved), reason)


def normalize_notification_row(item: Any, *, server_name: str) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    row = dict(item)
    params = row.get("params")
    if isinstance(params, Mapping):
        merged = dict(params)
        merged["method"] = str(row.get("method") or "").strip()
        merged.setdefault("server", str(params.get("server") or params.get("server_name") or server_name))
        merged.setdefault("server_name", str(params.get("server_name") or params.get("server") or server_name))
        return merged
    row.setdefault("server", server_name)
    row.setdefault("server_name", server_name)
    return row


def selected_server_names(*, entries: list[dict[str, Any]], server_name: str | None) -> list[str]:
    normalized = str(server_name or "").strip()
    names = [str(item.get("name") or "").strip() for item in entries if str(item.get("name") or "").strip()]
    if normalized:
        return [name for name in names if name == normalized]
    return names


def normalize_required_server_name(server_name: str) -> str:
    normalized = str(server_name or "").strip()
    if not normalized:
        raise ValueError("server name is required")
    return normalized


def normalize_optional_server_name(server_name: str | None) -> str | None:
    normalized = str(server_name or "").strip()
    return normalized or None


def target_names(target: str, entries: list[dict[str, Any]]) -> list[str]:
    key = str(target or "").strip()
    if not key:
        return []
    names = [str(item.get("name") or "").strip() for item in entries]
    names = [item for item in names if item]
    if key.lower() == "all":
        return names
    return [item for item in names if item == key]


def toggle_enabled_payload(
    *,
    target: str,
    enabled: bool,
    names: list[str],
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "ok",
        "target": target,
        "enabled": enabled,
        "servers": [item for item in entries if item.get("name") in names],
    }
