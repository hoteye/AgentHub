from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.slash_surface import surface_usage_text

from .mcp_commands_runtime_helpers_handlers_auth_helpers import (
    handle_mcp_auth_clear_impl,
    handle_mcp_auth_set_impl,
)
from .mcp_commands_runtime_helpers_invoke import (
    handle_mcp_tool_call_impl,
    invoke_mcp,
    invoke_mcp_runtime_with_typeerror_fallback,
)


def handle_mcp_list(
    runtime: Any,
    *,
    resolve_mcp_runtime: Callable[[Any], Any | None],
    invoke_first: Callable[..., Any],
    format_list_payload: Callable[[Any], str],
) -> tuple[str, list[Any]]:
    mcp_runtime = resolve_mcp_runtime(runtime)
    if mcp_runtime is None:
        return ("mcp runtime unavailable", [])
    payload, error = invoke_mcp(
        invoke_first,
        mcp_runtime,
        ("list_status", "list_servers", "list", "snapshot", "status"),
    )
    if error:
        return (error, [])
    return (format_list_payload(payload), [])


def handle_mcp_mutation(
    runtime: Any,
    action: str,
    target: str,
    *,
    resolve_mcp_runtime: Callable[[Any], Any | None],
    invoke_first: Callable[..., Any],
    format_action_payload: Callable[[str, str, Any], str],
) -> tuple[str, list[Any]]:
    mcp_runtime = resolve_mcp_runtime(runtime)
    if mcp_runtime is None:
        return ("mcp runtime unavailable", [])
    method_names = {
        "reconnect": ("reconnect", "reconnect_server"),
        "enable": ("enable", "enable_server"),
        "disable": ("disable", "disable_server"),
    }[action]
    payload, error = invoke_mcp(invoke_first, mcp_runtime, method_names, target)
    if error:
        return (error, [])
    return (format_action_payload(action, target, payload), [])


def handle_mcp_inspect(
    runtime: Any,
    target: str,
    *,
    resolve_mcp_runtime: Callable[[Any], Any | None],
    invoke_first: Callable[..., Any],
    format_inspect_payload: Callable[[str, Any], str],
) -> tuple[str, list[Any]]:
    mcp_runtime = resolve_mcp_runtime(runtime)
    if mcp_runtime is None:
        return ("mcp runtime unavailable", [])
    payload, error = invoke_mcp(
        invoke_first,
        mcp_runtime,
        ("inspect", "inspect_server", "server_status"),
        target,
    )
    if error:
        return (error, [])
    return (format_inspect_payload(target, payload), [])


def handle_mcp_auth(
    runtime: Any,
    arg_text: str,
    *,
    mode_hint: str,
    resolve_mcp_runtime: Callable[[Any], Any | None],
    parse_args: Callable[[Any, str], tuple[list[str], dict[str, Any]]],
    parse_headers_json_fn: Callable[[str], tuple[dict[str, str], str]],
    parse_callback_json_fn: Callable[[str], tuple[dict[str, Any], str]],
    handle_mcp_auth_set_fn: Callable[..., tuple[str, list[Any]]],
    handle_mcp_auth_clear_fn: Callable[..., tuple[str, list[Any]]],
) -> tuple[str, list[Any]]:
    mcp_runtime = resolve_mcp_runtime(runtime)
    if mcp_runtime is None:
        return ("mcp runtime unavailable", [])
    positionals, options = parse_args(runtime, arg_text)
    mode = str(mode_hint or "").strip().lower()
    cursor = 0
    if not mode:
        candidate = str(positionals[0] if positionals else "").strip().lower()
        if candidate in {"set", "callback", "clear"}:
            mode = candidate
            cursor = 1
        else:
            mode = "set"
    server_name = str(options.get("server") or options.get("server-name") or "").strip()
    if not server_name and len(positionals) > cursor:
        server_name = str(positionals[cursor] or "").strip()
    if not server_name:
        return (f"Usage: {surface_usage_text('mcp_auth')}", [])

    if mode == "clear":
        return handle_mcp_auth_clear_fn(mcp_runtime, server_name=server_name)

    token = str(options.get("token") or "").strip()
    if not token and len(positionals) > cursor + 1:
        token = str(positionals[cursor + 1] or "").strip()
    headers, headers_error = parse_headers_json_fn(str(options.get("headers-json") or options.get("headers_json") or ""))
    if headers_error:
        return (headers_error, [])
    callback_payload, callback_error = parse_callback_json_fn(str(options.get("callback-json") or options.get("callback_json") or ""))
    if callback_error:
        return (callback_error, [])
    callback_token = str(callback_payload.get("token") or callback_payload.get("access_token") or "").strip()
    if not token and callback_token:
        token = callback_token
    callback_headers = callback_payload.get("headers")
    if isinstance(callback_headers, dict):
        headers.update({str(key): str(value) for key, value in callback_headers.items()})
    if not token and not headers:
        return (f"Usage: {surface_usage_text('mcp_auth')}", [])

    return handle_mcp_auth_set_fn(
        mcp_runtime,
        server_name=server_name,
        token=token,
        headers=headers,
        callback_mode=(mode == "callback"),
    )


def handle_mcp_auth_set(
    mcp_runtime: Any,
    *,
    server_name: str,
    token: str,
    headers: dict[str, str],
    callback_mode: bool,
    invoke_first: Callable[..., Any],
    format_auth_payload: Callable[[str, Any, Any], str],
) -> tuple[str, list[Any]]:
    return handle_mcp_auth_set_impl(
        mcp_runtime,
        server_name=server_name,
        token=token,
        headers=headers,
        callback_mode=callback_mode,
        invoke_first=invoke_first,
        format_auth_payload=format_auth_payload,
    )


def handle_mcp_auth_clear(
    mcp_runtime: Any,
    *,
    server_name: str,
    invoke_first: Callable[..., Any],
    format_auth_payload: Callable[[str, Any, Any], str],
) -> tuple[str, list[Any]]:
    return handle_mcp_auth_clear_impl(
        mcp_runtime,
        server_name=server_name,
        invoke_first=invoke_first,
        format_auth_payload=format_auth_payload,
    )


def handle_mcp_resource(
    runtime: Any,
    arg_text: str,
    *,
    parse_args: Callable[[Any, str], tuple[list[str], dict[str, Any]]],
    resolve_mcp_runtime: Callable[[Any], Any | None],
    invoke_first: Callable[..., Any],
    format_resource_list_payload: Callable[[Any], str],
    format_resource_read_payload: Callable[[Any], str],
) -> tuple[str, list[Any]]:
    positionals, options = parse_args(runtime, arg_text)
    action = str(positionals[0] if positionals else "").strip().lower()
    mcp_runtime = resolve_mcp_runtime(runtime)
    if mcp_runtime is None:
        return ("mcp runtime unavailable", [])
    if action == "list":
        server_name = str(options.get("server") or options.get("server-name") or "").strip()
        if not server_name and len(positionals) > 1:
            server_name = str(positionals[1] or "").strip()
        payload, error = invoke_mcp(
            invoke_first,
            mcp_runtime,
            ("list_resources",),
            server_name=server_name or None,
        )
        if error:
            return (error, [])
        return (format_resource_list_payload(payload, server_name=server_name or None), [])
    if action == "read":
        server_name = str(options.get("server") or options.get("server-name") or "").strip()
        uri = str(options.get("uri") or "").strip()
        if not server_name and len(positionals) > 1:
            server_name = str(positionals[1] or "").strip()
        if not uri and len(positionals) > 2:
            uri = str(positionals[2] or "").strip()
        if not server_name or not uri:
            return (f"Usage: {surface_usage_text('mcp_resource_read')}", [])
        payload, error = invoke_mcp(
            invoke_first,
            mcp_runtime,
            ("read_resource",),
            server_name=server_name,
            uri=uri,
        )
        if error:
            return (error, [])
        return (format_resource_read_payload(payload), [])
    return (f"Usage: {surface_usage_text('mcp_resource')}", [])


def handle_mcp_tool_call(
    runtime: Any,
    arg_text: str,
    *,
    parse_args: Callable[[Any, str], tuple[list[str], dict[str, Any]]],
    resolve_mcp_runtime: Callable[[Any], Any | None],
    invoke_first: Callable[..., Any],
    format_projected_mcp_tool_call_fn: Callable[[Any], str],
) -> tuple[str, list[Any]]:
    return handle_mcp_tool_call_impl(
        runtime,
        arg_text,
        parse_args=parse_args,
        resolve_mcp_runtime=resolve_mcp_runtime,
        invoke_first=invoke_first,
        format_projected_mcp_tool_call_fn=format_projected_mcp_tool_call_fn,
    )


def handle_mcp_channel(
    runtime: Any,
    arg_text: str,
    *,
    resolve_mcp_runtime: Callable[[Any], Any | None],
    parse_args: Callable[[Any, str], tuple[list[str], dict[str, Any]]],
    invoke_first: Callable[..., Any],
    format_channel_list_payload: Callable[[Any], str],
) -> tuple[str, list[Any]]:
    mcp_runtime = resolve_mcp_runtime(runtime)
    if mcp_runtime is None:
        return ("mcp runtime unavailable", [])
    positionals, options = parse_args(runtime, arg_text)
    action = str(positionals[0] if positionals else "list").strip().lower()
    server_name = str(options.get("server") or options.get("server-name") or "").strip()
    if action not in {"", "list"}:
        return (f"Usage: {surface_usage_text('mcp_channel')}", [])
    if not server_name and len(positionals) > 1:
        server_name = str(positionals[1] or "").strip()
    payload, error = invoke_mcp_runtime_with_typeerror_fallback(
        invoke_first,
        mcp_runtime,
        ("list_channel_messages", "list_channels", "channels", "list_channel_requests", "list_channel_status"),
        fallback_args=(server_name or None,),
        server_name=server_name or None,
    )
    if error:
        return (error, [])
    return (format_channel_list_payload(payload, server_name=server_name or None), [])


def handle_mcp_permission(
    runtime: Any,
    arg_text: str,
    *,
    resolve_mcp_runtime: Callable[[Any], Any | None],
    parse_args: Callable[[Any, str], tuple[list[str], dict[str, Any]]],
    invoke_first: Callable[..., Any],
    parse_bool_flag_fn: Callable[[str], bool | None],
    format_permission_list_payload: Callable[[Any], str],
    format_permission_respond_payload: Callable[..., str],
) -> tuple[str, list[Any]]:
    mcp_runtime = resolve_mcp_runtime(runtime)
    if mcp_runtime is None:
        return ("mcp runtime unavailable", [])
    positionals, options = parse_args(runtime, arg_text)
    action = str(positionals[0] if positionals else "").strip().lower()
    if action == "list":
        server_name = str(options.get("server") or options.get("server-name") or "").strip()
        if not server_name and len(positionals) > 1:
            server_name = str(positionals[1] or "").strip()
        payload, error = invoke_mcp_runtime_with_typeerror_fallback(
            invoke_first,
            mcp_runtime,
            ("list_permission_requests", "list_permissions", "permissions"),
            fallback_args=(server_name or None,),
            server_name=server_name or None,
        )
        if error:
            return (error, [])
        return (format_permission_list_payload(payload, server_name=server_name or None), [])
    if action == "respond":
        server_name = str(options.get("server") or options.get("server-name") or "").strip()
        request_id = str(options.get("request-id") or options.get("request_id") or "").strip()
        approved_text = str(options.get("approved") or "").strip()
        reason = str(options.get("reason") or "").strip()
        if not server_name and len(positionals) > 1:
            server_name = str(positionals[1] or "").strip()
        if not request_id and len(positionals) > 2:
            request_id = str(positionals[2] or "").strip()
        if not approved_text and len(positionals) > 3:
            approved_text = str(positionals[3] or "").strip()
        approved = parse_bool_flag_fn(approved_text)
        if not server_name or not request_id or approved is None:
            return (
                f"Usage: {surface_usage_text('mcp_permission_respond')}",
                [],
            )
        payload, error = invoke_mcp_runtime_with_typeerror_fallback(
            invoke_first,
            mcp_runtime,
            ("respond_permission_request", "respond_permission", "respond_to_permission", "permission_respond"),
            fallback_args=(server_name, request_id, approved, reason or None),
            server_name=server_name,
            request_id=request_id,
            approved=approved,
            reason=reason or None,
        )
        if error:
            return (error, [])
        return (format_permission_respond_payload(payload, server_name=server_name, request_id=request_id, approved=approved), [])
    return (f"Usage: {surface_usage_text('mcp_permission')}", [])
