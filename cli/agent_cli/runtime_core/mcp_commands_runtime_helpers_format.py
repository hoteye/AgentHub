from __future__ import annotations

from typing import Any, Callable


def format_mcp_list_payload(payload: Any) -> str:
    entries: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        raw_entries = payload.get("servers")
        if raw_entries is None:
            raw_entries = payload.get("items")
        if raw_entries is None:
            raw_entries = payload.get("mcp_servers")
        if isinstance(raw_entries, dict):
            for name, item in raw_entries.items():
                row = dict(item) if isinstance(item, dict) else {"value": item}
                row.setdefault("name", str(name))
                entries.append(row)
        elif isinstance(raw_entries, list):
            entries = [dict(item) for item in raw_entries if isinstance(item, dict)]
    elif isinstance(payload, list):
        entries = [dict(item) for item in payload if isinstance(item, dict)]

    lines = ["mcp servers"]
    lines.append(f"count={len(entries)}")
    if not entries:
        lines.append("servers=-")
        return "\n".join(lines)
    for item in entries:
        name = str(item.get("name") or item.get("server") or "-").strip() or "-"
        status = str(item.get("status") or "-").strip() or "-"
        enabled_value = item.get("enabled")
        enabled = "-" if enabled_value is None else ("true" if bool(enabled_value) else "false")
        lines.append(f"{name} status={status} enabled={enabled}")
    return "\n".join(lines)


def format_mcp_channel_list_payload(
    payload: Any,
    *,
    server_name: str | None,
    normalize_payload_items_fn: Callable[[Any, tuple[str, ...]], list[dict[str, Any]]],
) -> str:
    items = normalize_payload_items_fn(payload, ("channels", "items", "requests", "permissions"))
    lines = ["mcp channels"]
    lines.append(f"server={server_name or '-'}")
    lines.append(f"count={len(items)}")
    for item in items:
        server = str(item.get("server") or item.get("server_name") or server_name or "-").strip() or "-"
        name = str(item.get("channel") or item.get("name") or item.get("id") or "-").strip() or "-"
        status = str(item.get("status") or "-").strip() or "-"
        lines.append(f"server={server} channel={name} status={status}")
    return "\n".join(lines)


def format_mcp_permission_list_payload(
    payload: Any,
    *,
    server_name: str | None,
    normalize_payload_items_fn: Callable[[Any, tuple[str, ...]], list[dict[str, Any]]],
) -> str:
    items = normalize_payload_items_fn(payload, ("permissions", "requests", "items"))
    lines = ["mcp permissions"]
    lines.append(f"server={server_name or '-'}")
    lines.append(f"count={len(items)}")
    for item in items:
        server = str(item.get("server") or item.get("server_name") or server_name or "-").strip() or "-"
        request_id = str(item.get("request_id") or item.get("request-id") or item.get("id") or "-").strip() or "-"
        approved_value = item.get("approved")
        approved = "-" if approved_value is None else ("true" if bool(approved_value) else "false")
        status = str(item.get("status") or "-").strip() or "-"
        lines.append(f"server={server} request_id={request_id} approved={approved} status={status}")
    return "\n".join(lines)


def format_mcp_permission_respond_payload(
    payload: Any,
    *,
    server_name: str,
    request_id: str,
    approved: bool,
) -> str:
    data = dict(payload or {}) if isinstance(payload, dict) else {}
    lines = ["mcp permission respond"]
    lines.append(f"server={str(data.get('server') or data.get('server_name') or server_name).strip() or '-'}")
    lines.append(f"request_id={str(data.get('request_id') or data.get('request-id') or request_id).strip() or '-'}")
    lines.append(
        f"approved={'true' if bool(data.get('approved')) else 'false' if data.get('approved') is not None else ('true' if approved else 'false')}"
    )
    status = str(data.get("status") or "").strip()
    if status:
        lines.append(f"status={status}")
    reason = str(data.get("reason") or "").strip()
    if reason:
        lines.append(f"reason={reason}")
    return "\n".join(lines)


def format_mcp_action_payload(action: str, target: str, payload: Any) -> str:
    lines = [f"mcp {action} requested"]
    lines.append(f"target={target}")
    if isinstance(payload, dict):
        lines.append(f"status={payload.get('status') or '-'}")
        reason = str(payload.get("reason") or "").strip()
        if reason:
            lines.append(f"reason={reason}")
    return "\n".join(lines)


def format_mcp_inspect_payload(target: str, payload: Any) -> str:
    lines = ["mcp server inspect"]
    lines.append(f"target={target}")
    if isinstance(payload, dict):
        lines.append(f"status={payload.get('status') or '-'}")
        enabled = payload.get("enabled")
        if enabled is not None:
            lines.append(f"enabled={'true' if bool(enabled) else 'false'}")
        scope = str(payload.get("scope") or "").strip()
        if scope:
            lines.append(f"scope={scope}")
        reason = str(payload.get("reason") or "").strip()
        if reason:
            lines.append(f"reason={reason}")
        last_error = str(payload.get("last_error") or "").strip()
        if last_error:
            lines.append(f"last_error={last_error}")
    return "\n".join(lines)


def format_mcp_auth_payload(
    target: str,
    reconnect_payload: Any,
    inspect_payload: Any,
    *,
    callback_mode: bool,
    cleared: bool,
) -> str:
    lines = ["mcp auth updated"]
    lines.append(f"target={target}")
    lines.append(f"mode={'callback' if callback_mode else ('clear' if cleared else 'set')}")
    if isinstance(reconnect_payload, dict):
        reconnect_status = str(reconnect_payload.get("status") or "").strip()
        if reconnect_status:
            lines.append(f"reconnect={reconnect_status}")
    if isinstance(inspect_payload, dict):
        status = str(inspect_payload.get("status") or "").strip()
        if status:
            lines.append(f"status={status}")
        enabled = inspect_payload.get("enabled")
        if enabled is not None:
            lines.append(f"enabled={'true' if bool(enabled) else 'false'}")
    return "\n".join(lines)


def format_mcp_resource_list_payload(payload: Any, *, server_name: str | None) -> str:
    items = [dict(item) for item in list(payload or []) if isinstance(item, dict)]
    lines = ["mcp resources"]
    lines.append(f"server={server_name or '-'}")
    lines.append(f"count={len(items)}")
    for item in items:
        lines.append(
            f"{str(item.get('server_name') or '-')} {str(item.get('uri') or '-')} {str(item.get('name') or '').strip()}".rstrip()
        )
    return "\n".join(lines)


def format_mcp_resource_read_payload(payload: Any) -> str:
    data = dict(payload or {}) if isinstance(payload, dict) else {}
    lines = ["mcp resource read"]
    lines.append(f"ok={'true' if bool(data.get('ok')) else 'false'}")
    lines.append(f"server={str(data.get('server_name') or '-').strip() or '-'}")
    lines.append(f"uri={str(data.get('uri') or '-').strip() or '-'}")
    if data.get("error"):
        lines.append(f"error={str(data.get('error') or '').strip()}")
    mime_type = str(data.get("mime_type") or "").strip()
    if mime_type:
        lines.append(f"mime_type={mime_type}")
    contents = data.get("contents")
    if isinstance(contents, list):
        lines.append(f"contents={len(contents)}")
    return "\n".join(lines)
