from __future__ import annotations

import json
from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar.errors import (
    CodexSidecarProtocolError,
    CodexSidecarRequestError,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import (
    JsonObject,
    JsonRpcNotification,
    JsonRpcServerRequest,
)

PROTOCOL_ERROR_METHOD = "$agenthub/protocolError"
UNMATCHED_RESPONSE_METHOD = "$agenthub/unmatchedResponse"

_MISSING = object()


def is_notification(payload: JsonObject) -> bool:
    return "method" in payload and "id" not in payload


def is_server_request(payload: JsonObject) -> bool:
    return "method" in payload and "id" in payload and "params" in payload


def notification_from_payload(payload: JsonObject) -> JsonRpcNotification:
    method = str(payload.get("method") or "")
    if not method:
        raise CodexSidecarProtocolError("notification method is required")
    params = payload.get("params")
    return JsonRpcNotification(
        method=method,
        params=dict(params or {}) if isinstance(params, dict) else {"value": params},
        raw=payload,
    )


def server_request_from_payload(payload: JsonObject) -> JsonRpcServerRequest:
    method = str(payload.get("method") or "")
    if not method:
        raise CodexSidecarProtocolError("server request method is required")
    request_id = payload.get("id")
    if not isinstance(request_id, int | str):
        raise CodexSidecarProtocolError("server request id is required")
    params = payload.get("params")
    return JsonRpcServerRequest(
        request_id=request_id,
        method=method,
        params=dict(params or {}) if isinstance(params, dict) else {"value": params},
        raw=payload,
    )


def response_request_id_from_payload(payload: JsonObject) -> int:
    raw_request_id = payload.get("id")
    if isinstance(raw_request_id, int):
        return raw_request_id
    if isinstance(raw_request_id, str) and raw_request_id.isdigit():
        return int(raw_request_id)
    raise CodexSidecarProtocolError("JSON-RPC response id is required")


def response_result_or_raise(payload: JsonObject) -> JsonObject:
    if "error" in payload:
        error = payload.get("error")
        message = (
            str(error.get("message") or "JSON-RPC error")
            if isinstance(error, dict)
            else "JSON-RPC error"
        )
        raise CodexSidecarRequestError(f"{message}: {json.dumps(error, ensure_ascii=False)}")
    result = payload.get("result")
    return dict(result or {}) if isinstance(result, dict) else {"value": result}


def make_protocol_error_notification(
    error: str,
    *,
    payload: JsonObject | None = None,
    line: str | None = None,
    value: Any = _MISSING,
    raw: JsonObject | None = None,
) -> JsonRpcNotification:
    params: JsonObject = {"error": error}
    if payload is not None:
        params["payload"] = payload
    if line is not None:
        params["line"] = line
    if value is not _MISSING:
        params["value"] = value
    if raw is None:
        return JsonRpcNotification(method=PROTOCOL_ERROR_METHOD, params=params)
    return JsonRpcNotification(method=PROTOCOL_ERROR_METHOD, params=params, raw=raw)


def make_unmatched_response_notification(
    request_id: int,
    payload: JsonObject,
) -> JsonRpcNotification:
    return JsonRpcNotification(
        method=UNMATCHED_RESPONSE_METHOD,
        params={"requestId": request_id, "payload": payload},
        raw=payload,
    )
