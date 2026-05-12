from __future__ import annotations

import json
from typing import Any, Callable


_METHOD_HANDLER_NAMES_WITH_PARAMS: dict[str, str] = {
    "session/run": "_handle_session_run",
    "session/start": "_handle_session_start",
    "thread/start": "_handle_thread_start",
    "thread/list": "_handle_thread_list",
    "thread/resume": "_handle_thread_resume",
    "thread/read": "_handle_thread_read",
    "thread/fork": "_handle_thread_fork",
    "turn/start": "_handle_turn_start",
    "model/list": "_handle_model_list",
    "mcpServerStatus/list": "_handle_mcp_server_status_list",
    "action/execute": "_handle_action_execute",
    "command/exec": "_handle_command_exec",
    "command/start": "_handle_command_start",
    "command/writeStdin": "_handle_command_write_stdin",
    "command/terminate": "_handle_command_terminate",
}

_METHOD_HANDLER_NAMES_WITHOUT_PARAMS: dict[str, str] = {
    "session/interrupt": "_handle_session_interrupt",
    "session/providerStatus": "_handle_provider_status",
    "tools/list": "_handle_tools_list",
}


def _emit_invalid_request(server: Any, *, request_id: Any, detail: str) -> None:
    server._emit_error_response(
        request_id=request_id,
        code=-32600,
        message="Invalid Request",
        data={"detail": detail},
    )


def _emit_invalid_params(
    server: Any,
    *,
    request_id: Any,
    message: str,
    detail: str,
) -> None:
    server._emit_error_response(
        request_id=request_id,
        code=-32602,
        message=message,
        data={"detail": detail},
    )


def _dispatch_ready_method(
    server: Any,
    *,
    method: str,
    request_id: Any,
    params: dict[str, Any],
    gateway_dispatcher_supports_method_fn: Callable[[str], bool],
) -> bool:
    handler_name = _METHOD_HANDLER_NAMES_WITH_PARAMS.get(method)
    if handler_name is not None:
        getattr(server, handler_name)(request_id, params)
        return True
    handler_name = _METHOD_HANDLER_NAMES_WITHOUT_PARAMS.get(method)
    if handler_name is not None:
        getattr(server, handler_name)(request_id)
        return True
    if gateway_dispatcher_supports_method_fn(method):
        server._handle_gateway_method(request_id, method, params)
        return True
    if method == "server/ping":
        server._emit_result(request_id, {"ok": True})
        return True
    return False


def handle_line(
    server: Any,
    line: str,
    *,
    unsupported_reference_method_error_data_fn: Callable[[str], dict[str, Any] | None],
    gateway_dispatcher_supports_method_fn: Callable[[str], bool],
    invalid_params_message: str,
    invalid_params_detail: str,
    not_initialized_message: str,
    not_initialized_detail: str,
) -> None:
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        server._emit_error_response(
            request_id=None,
            code=-32700,
            message="Parse error",
            data={"detail": str(exc)},
        )
        return

    if not isinstance(message, dict):
        _emit_invalid_request(server, request_id=None, detail="message must be a JSON object")
        return

    if server._handle_server_request_response(message):
        return

    method = str(message.get("method") or "").strip()
    request_id = message.get("id")
    params = message.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        _emit_invalid_params(
            server,
            request_id=request_id,
            message=invalid_params_message,
            detail=invalid_params_detail,
        )
        return

    if not method:
        _emit_invalid_request(server, request_id=request_id, detail="method is required")
        return

    if method == "initialized":
        server._handle_initialized_notification(params)
        return

    if method == "initialize":
        server._handle_initialize(request_id, params)
        return

    if not (server.state.initialized and server.state.initialized_notification_received):
        server._emit_error_response(
            request_id=request_id,
            code=-32002,
            message=not_initialized_message,
            data={"detail": not_initialized_detail},
        )
        return

    if _dispatch_ready_method(
        server,
        method=method,
        request_id=request_id,
        params=params,
        gateway_dispatcher_supports_method_fn=gateway_dispatcher_supports_method_fn,
    ):
        return

    unsupported_data = unsupported_reference_method_error_data_fn(method)
    if unsupported_data is not None:
        server._emit_error_response(
            request_id=request_id,
            code=-32601,
            message="Method not found",
            data=unsupported_data,
        )
        return

    server._emit_error_response(
        request_id=request_id,
        code=-32601,
        message="Method not found",
        data={"detail": method},
    )


def handle_initialized_notification(server: Any, params: dict[str, Any]) -> None:
    if not server.state.initialized:
        return
    server.state.initialized_notification_received = True
    if params:
        server.state.client_info["initialized_params"] = params


def handle_initialize(
    server: Any,
    request_id: Any,
    params: dict[str, Any],
    *,
    version: str,
    app_server_capability_methods_fn: Callable[[], list[str]],
) -> None:
    if server.state.initialized:
        server._emit_error_response(
            request_id=request_id,
            code=-32001,
            message="Already initialized",
        )
        return
    client_info = params.get("clientInfo")
    if isinstance(client_info, dict):
        server.state.client_info = dict(client_info)
    server.state.initialized = True
    server.state.initialized_notification_received = False
    provider_status = server.runtime.agent.provider_status()
    server._emit_result(
        request_id,
        {
            "serverInfo": {
                "name": "agent_cli_app_server",
                "version": version,
            },
            "platformFamily": provider_status.get("platform_family") or "-",
            "platformOs": provider_status.get("platform_os") or "-",
            "shellKind": provider_status.get("shell_kind") or "-",
            "providerLabel": provider_status.get("provider_label") or "-",
            "capabilities": {
                "methods": app_server_capability_methods_fn()
            },
        },
    )


__all__ = [
    "handle_initialize",
    "handle_initialized_notification",
    "handle_line",
]
