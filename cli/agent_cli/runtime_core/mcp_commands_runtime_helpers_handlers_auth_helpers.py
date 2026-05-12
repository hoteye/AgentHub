from __future__ import annotations

from typing import Any, Callable

from .mcp_commands_runtime_helpers_invoke import invoke_mcp


def handle_mcp_auth_set_impl(
    mcp_runtime: Any,
    *,
    server_name: str,
    token: str,
    headers: dict[str, str],
    callback_mode: bool,
    invoke_first: Callable[..., Any],
    format_auth_payload: Callable[[str, Any, Any], str],
) -> tuple[str, list[Any]]:
    inspect_payload, error = invoke_mcp(
        invoke_first,
        mcp_runtime,
        ("inspect", "inspect_server", "server_status"),
        server_name,
    )
    if error:
        return (error, [])
    config_payload = dict(inspect_payload.get("config") or {}) if isinstance(inspect_payload, dict) else {}
    auth_payload = dict(config_payload.get("auth") or {}) if isinstance(config_payload.get("auth"), dict) else {}
    if token:
        auth_payload["token"] = token
    if headers:
        merged_headers = dict(auth_payload.get("headers") or {}) if isinstance(auth_payload.get("headers"), dict) else {}
        merged_headers.update(headers)
        auth_payload["headers"] = merged_headers
    if callback_mode:
        callback_state = dict(auth_payload.get("callback") or {}) if isinstance(auth_payload.get("callback"), dict) else {}
        callback_state["received"] = True
        auth_payload["callback"] = callback_state
    config_payload["auth"] = auth_payload
    set_runtime_dynamic = getattr(mcp_runtime, "set_runtime_dynamic", None)
    if not callable(set_runtime_dynamic):
        return ("mcp runtime unavailable", [])
    set_runtime_dynamic(server_name, config_payload)
    reconnect_payload, error = invoke_mcp(
        invoke_first,
        mcp_runtime,
        ("reconnect", "reconnect_server"),
        server_name,
    )
    if error:
        return (error, [])
    inspect_after, error = invoke_mcp(
        invoke_first,
        mcp_runtime,
        ("inspect", "inspect_server", "server_status"),
        server_name,
    )
    if error:
        return (error, [])
    return (format_auth_payload(server_name, reconnect_payload, inspect_after, callback_mode=callback_mode, cleared=False), [])


def handle_mcp_auth_clear_impl(
    mcp_runtime: Any,
    *,
    server_name: str,
    invoke_first: Callable[..., Any],
    format_auth_payload: Callable[[str, Any, Any], str],
) -> tuple[str, list[Any]]:
    inspect_payload, error = invoke_mcp(
        invoke_first,
        mcp_runtime,
        ("inspect", "inspect_server", "server_status"),
        server_name,
    )
    if error:
        return (error, [])
    config_payload = dict(inspect_payload.get("config") or {}) if isinstance(inspect_payload, dict) else {}
    config_payload.pop("auth", None)
    set_runtime_dynamic = getattr(mcp_runtime, "set_runtime_dynamic", None)
    if not callable(set_runtime_dynamic):
        return ("mcp runtime unavailable", [])
    set_runtime_dynamic(server_name, config_payload)
    reconnect_payload, error = invoke_mcp(
        invoke_first,
        mcp_runtime,
        ("reconnect", "reconnect_server"),
        server_name,
    )
    if error:
        return (error, [])
    inspect_after, error = invoke_mcp(
        invoke_first,
        mcp_runtime,
        ("inspect", "inspect_server", "server_status"),
        server_name,
    )
    if error:
        return (error, [])
    return (format_auth_payload(server_name, reconnect_payload, inspect_after, callback_mode=False, cleared=True), [])
