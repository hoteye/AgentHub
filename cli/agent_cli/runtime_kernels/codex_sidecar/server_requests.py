from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonObject, JsonRpcServerRequest

CodexServerRequestKind = Literal[
    "command_execution_approval",
    "file_change_approval",
    "permission_approval",
    "tool_user_input",
    "mcp_elicitation",
    "dynamic_tool_call",
    "auth_token_refresh",
    "legacy_apply_patch_approval",
    "legacy_exec_command_approval",
    "unsupported",
]

CODEX_SERVER_REQUEST_METHOD_KINDS: dict[str, CodexServerRequestKind] = {
    "item/commandExecution/requestApproval": "command_execution_approval",
    "item/fileChange/requestApproval": "file_change_approval",
    "item/permissions/requestApproval": "permission_approval",
    "item/tool/requestUserInput": "tool_user_input",
    "mcpServer/elicitation/request": "mcp_elicitation",
    "item/tool/call": "dynamic_tool_call",
    "account/chatgptAuthTokens/refresh": "auth_token_refresh",
    "applyPatchApproval": "legacy_apply_patch_approval",
    "execCommandApproval": "legacy_exec_command_approval",
}


@dataclass(slots=True)
class CodexServerRequestEnvelope:
    request_id: int | str
    method: str
    kind: CodexServerRequestKind
    thread_id: str = ""
    turn_id: str = ""
    item_id: str = ""
    tab_id: str = ""
    runtime_id: str = ""
    params: JsonObject = field(default_factory=dict)
    raw: JsonObject = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    status: str = "pending"

    @property
    def registry_key(self) -> str:
        return str(self.request_id)

    def to_event(self) -> JsonObject:
        return {
            "request_id": self.request_id,
            "method": self.method,
            "kind": self.kind,
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "item_id": self.item_id,
            "tab_id": self.tab_id,
            "runtime_id": self.runtime_id,
            "created_at": self.created_at,
            "status": self.status,
        }


class CodexServerRequestHandler(Protocol):
    def __call__(self, runtime: Any, envelope: CodexServerRequestEnvelope) -> JsonObject | None: ...


class CodexServerRequestRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, CodexServerRequestHandler] = {}
        self._pending: dict[str, CodexServerRequestEnvelope] = {}
        self._lock = threading.Lock()

    def register(self, method: str, handler: CodexServerRequestHandler) -> None:
        normalized = str(method or "").strip()
        if not normalized:
            raise ValueError("server request method is required")
        self._handlers[normalized] = handler

    def dispatch(
        self,
        runtime: Any,
        request: JsonRpcServerRequest,
        *,
        respond: Callable[[JsonRpcServerRequest, JsonObject], None],
        unsupported_response: Callable[[CodexServerRequestEnvelope], JsonObject] | None = None,
    ) -> CodexServerRequestEnvelope:
        envelope = envelope_from_server_request(request, runtime=runtime)
        self.mark_pending(envelope)
        handler = self._handlers.get(envelope.method)
        try:
            if handler is None:
                envelope.status = "unsupported"
                response = (
                    unsupported_response(envelope)
                    if unsupported_response is not None
                    else unsupported_server_request_response(envelope)
                )
                respond(request, response)
                self.resolve(envelope.request_id, status="unsupported")
                return envelope
            result = handler(runtime, envelope)
            envelope.status = "pending" if result is None else "responded"
            if result is not None:
                respond(request, result)
                self.resolve(envelope.request_id, status="responded")
            return envelope
        except Exception as exc:
            envelope.status = "failed"
            respond(request, server_request_error_response(envelope, str(exc)))
            self.resolve(envelope.request_id, status="failed")
            return envelope

    def mark_pending(self, envelope: CodexServerRequestEnvelope) -> CodexServerRequestEnvelope:
        with self._lock:
            self._pending[envelope.registry_key] = envelope
        return envelope

    def resolve(self, request_id: int | str, *, status: str = "resolved") -> None:
        key = str(request_id)
        with self._lock:
            envelope = self._pending.pop(key, None)
        if envelope is not None:
            envelope.status = status

    def get(self, request_id: int | str) -> CodexServerRequestEnvelope | None:
        with self._lock:
            return self._pending.get(str(request_id))

    def pending(self) -> list[CodexServerRequestEnvelope]:
        with self._lock:
            return list(self._pending.values())


def envelope_from_server_request(
    request: JsonRpcServerRequest,
    *,
    runtime: Any | None = None,
) -> CodexServerRequestEnvelope:
    params = dict(request.params or {})
    return CodexServerRequestEnvelope(
        request_id=request.request_id,
        method=str(request.method or "").strip(),
        kind=kind_for_method(str(request.method or "").strip()),
        thread_id=_param_text(params, "threadId", "thread_id", "conversationId"),
        turn_id=_param_text(params, "turnId", "turn_id"),
        item_id=_param_text(params, "itemId", "item_id", "callId", "call_id"),
        tab_id=str(getattr(runtime, "tab_id", "") or "").strip(),
        runtime_id=str(id(runtime)) if runtime is not None else "",
        params=params,
        raw=dict(request.raw or {}),
    )


def kind_for_method(method: str) -> CodexServerRequestKind:
    return CODEX_SERVER_REQUEST_METHOD_KINDS.get(str(method or "").strip(), "unsupported")


def unsupported_server_request_response(envelope: CodexServerRequestEnvelope) -> JsonObject:
    return server_request_error_response(
        envelope,
        f"unsupported sidecar server request: {envelope.method}",
        code=-32601,
    )


def server_request_error_response(
    envelope: CodexServerRequestEnvelope,
    message: str,
    *,
    code: int = -32000,
) -> JsonObject:
    return {
        "error": {
            "code": code,
            "message": message,
            "data": {
                "requestId": envelope.request_id,
                "method": envelope.method,
                "kind": envelope.kind,
                "threadId": envelope.thread_id,
                "turnId": envelope.turn_id,
                "itemId": envelope.item_id,
            },
        }
    }


def _param_text(params: JsonObject, *keys: str) -> str:
    for key in keys:
        value = params.get(key)
        if value is None:
            continue
        text = str(value or "").strip()
        if text:
            return text
    return ""
