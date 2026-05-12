from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


McpMessage = dict[str, Any]
EmitMessage = Callable[[dict[str, Any]], None]
ServerMessageHandler = Callable[[McpMessage], McpMessage]

MCP_BRIDGE_METHOD = "mcp/message"
MCP_BRIDGE_RESPONSE_ERROR_CODE = -32060
MCP_BRIDGE_DISCONNECTED_ERROR_CODE = -32061


@dataclass
class _PendingMcpRequest:
    request_id: str
    server_name: str
    message: McpMessage
    response_event: threading.Event = field(default_factory=threading.Event)
    response_payload: McpMessage | None = None
    response_error: dict[str, Any] | None = None


def handle_mcp_response_message(
    *,
    message: dict[str, Any],
    pending_requests_lock: threading.Lock,
    pending_requests: dict[str, _PendingMcpRequest],
) -> bool:
    if "method" in message:
        return False
    request_id = message.get("id")
    if request_id is None:
        return False
    request_key = str(request_id)
    with pending_requests_lock:
        pending = pending_requests.get(request_key)
    if pending is None:
        return False

    result = message.get("result")
    error = message.get("error")

    if isinstance(result, dict):
        payload = result.get("message", result)
        pending.response_payload = dict(payload) if isinstance(payload, dict) else {}
    else:
        pending.response_payload = {}
    pending.response_error = dict(error) if isinstance(error, dict) else None
    pending.response_event.set()
    return True


def abort_pending_mcp_requests(
    *,
    pending_requests_lock: threading.Lock,
    pending_requests: dict[str, _PendingMcpRequest],
) -> None:
    with pending_requests_lock:
        pending_items = list(pending_requests.values())
        pending_requests.clear()
    for pending in pending_items:
        pending.response_error = {
            "code": MCP_BRIDGE_DISCONNECTED_ERROR_CODE,
            "message": "Bridge closed before response was received",
        }
        pending.response_event.set()


class SdkMcpClientBridge:
    def __init__(self, *, emit: EmitMessage) -> None:
        self._emit = emit
        self._closed = False
        self._pending_requests_lock = threading.Lock()
        self._pending_requests: dict[str, _PendingMcpRequest] = {}

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        abort_pending_mcp_requests(
            pending_requests_lock=self._pending_requests_lock,
            pending_requests=self._pending_requests,
        )

    def handle_response_message(self, message: dict[str, Any]) -> bool:
        return handle_mcp_response_message(
            message=message,
            pending_requests_lock=self._pending_requests_lock,
            pending_requests=self._pending_requests,
        )

    def send(
        self,
        *,
        server_name: str,
        message: McpMessage,
        timeout_sec: float | None = None,
    ) -> McpMessage:
        if self._closed:
            raise RuntimeError("SDK MCP bridge is closed")
        normalized_server_name = str(server_name or "").strip()
        if not normalized_server_name:
            raise ValueError("server_name is required")
        request_id = f"mcp_req_{uuid.uuid4().hex}"
        pending = _PendingMcpRequest(
            request_id=request_id,
            server_name=normalized_server_name,
            message=dict(message or {}),
        )
        with self._pending_requests_lock:
            self._pending_requests[request_id] = pending
        try:
            self._emit(
                {
                    "id": request_id,
                    "method": MCP_BRIDGE_METHOD,
                    "params": {
                        "serverName": pending.server_name,
                        "message": pending.message,
                    },
                }
            )
            pending.response_event.wait(timeout=timeout_sec)
            if not pending.response_event.is_set():
                raise TimeoutError("Timed out waiting for MCP bridge response")
            if pending.response_error is not None:
                code = int(pending.response_error.get("code") or MCP_BRIDGE_RESPONSE_ERROR_CODE)
                detail = str(pending.response_error.get("message") or "MCP bridge request failed")
                raise RuntimeError(f"[{code}] {detail}")
            return dict(pending.response_payload or {})
        finally:
            with self._pending_requests_lock:
                self._pending_requests.pop(request_id, None)


class SdkMcpServerBridge:
    def __init__(self, *, emit: EmitMessage) -> None:
        self._emit = emit
        self._handlers: dict[str, ServerMessageHandler] = {}

    def register_handler(self, server_name: str, handler: ServerMessageHandler) -> None:
        key = str(server_name or "").strip()
        if not key:
            raise ValueError("server_name is required")
        self._handlers[key] = handler

    def handle_request_message(self, message: dict[str, Any]) -> bool:
        if str(message.get("method") or "") != MCP_BRIDGE_METHOD:
            return False
        request_id = message.get("id")
        params = message.get("params")
        if request_id is None or not isinstance(params, dict):
            return False

        server_name = str(params.get("serverName") or "").strip()
        payload = params.get("message")
        if not server_name or not isinstance(payload, dict):
            self._emit(
                {
                    "id": request_id,
                    "error": {
                        "code": MCP_BRIDGE_RESPONSE_ERROR_CODE,
                        "message": "Invalid MCP bridge request payload",
                    },
                }
            )
            return True

        handler = self._handlers.get(server_name)
        if handler is None:
            self._emit(
                {
                    "id": request_id,
                    "error": {
                        "code": MCP_BRIDGE_RESPONSE_ERROR_CODE,
                        "message": f'No MCP handler registered for "{server_name}"',
                    },
                }
            )
            return True

        try:
            response_payload = handler(dict(payload))
        except Exception as exc:
            self._emit(
                {
                    "id": request_id,
                    "error": {
                        "code": MCP_BRIDGE_RESPONSE_ERROR_CODE,
                        "message": f"{type(exc).__name__}: {exc}",
                    },
                }
            )
            return True

        self._emit(
            {
                "id": request_id,
                "result": {
                    "serverName": server_name,
                    "message": dict(response_payload or {}),
                },
            }
        )
        return True
