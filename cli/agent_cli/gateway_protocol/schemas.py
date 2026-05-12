from __future__ import annotations

from typing import Any, Dict

from .errors import ErrorShape
from .frames import (
    PROTOCOL_VERSION,
    ErrorFrame,
    EventFrame,
    GatewayFrame,
    RequestFrame,
    SuccessFrame,
    error_frame,
    event_frame,
    request_frame,
    success_frame,
)


def _require_mapping(payload: Any, *, label: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return dict(payload)


def _require_protocol_version(payload: Dict[str, Any]) -> None:
    version = str(payload.get("protocol_version") or "").strip()
    if version != PROTOCOL_VERSION:
        raise ValueError(f"unsupported protocol_version: {version or '<missing>'}")


def parse_request_frame(payload: Any) -> RequestFrame:
    mapping = _require_mapping(payload, label="request frame")
    _require_protocol_version(mapping)
    return request_frame(
        request_id=str(mapping.get("request_id") or "").strip(),
        method=str(mapping.get("method") or "").strip(),
        params=mapping.get("params") if isinstance(mapping.get("params"), dict) else {},
        metadata=mapping.get("metadata") if isinstance(mapping.get("metadata"), dict) else {},
    )


def parse_success_frame(payload: Any) -> SuccessFrame:
    mapping = _require_mapping(payload, label="success frame")
    _require_protocol_version(mapping)
    if mapping.get("ok") is not True:
        raise ValueError("success frame must set ok=true")
    return success_frame(
        request_id=str(mapping.get("request_id") or "").strip(),
        result=mapping.get("result") if isinstance(mapping.get("result"), dict) else {},
        metadata=mapping.get("metadata") if isinstance(mapping.get("metadata"), dict) else {},
    )


def parse_error_frame(payload: Any) -> ErrorFrame:
    mapping = _require_mapping(payload, label="error frame")
    _require_protocol_version(mapping)
    if mapping.get("ok") is not False:
        raise ValueError("error frame must set ok=false")
    error_payload = _require_mapping(mapping.get("error"), label="error shape")
    error = ErrorShape(
        code=str(error_payload.get("code") or "").strip().upper(),
        message=str(error_payload.get("message") or "").strip(),
        details=error_payload.get("details"),
        retryable=bool(error_payload.get("retryable", False)),
        retry_after_ms=(
            int(error_payload["retry_after_ms"])
            if error_payload.get("retry_after_ms") is not None
            else None
        ),
    )
    if not error.code or not error.message:
        raise ValueError("error frame requires error.code and error.message")
    return error_frame(
        request_id=str(mapping.get("request_id") or "").strip(),
        error=error,
        metadata=mapping.get("metadata") if isinstance(mapping.get("metadata"), dict) else {},
    )


def parse_event_frame(payload: Any) -> EventFrame:
    mapping = _require_mapping(payload, label="event frame")
    _require_protocol_version(mapping)
    return event_frame(
        event_type=str(mapping.get("event_type") or "").strip(),
        data=mapping.get("data") if isinstance(mapping.get("data"), dict) else {},
        metadata=mapping.get("metadata") if isinstance(mapping.get("metadata"), dict) else {},
    )


def parse_gateway_frame(payload: Any) -> GatewayFrame:
    mapping = _require_mapping(payload, label="gateway frame")
    if "method" in mapping:
        return parse_request_frame(mapping)
    if "event_type" in mapping:
        return parse_event_frame(mapping)
    if "error" in mapping:
        return parse_error_frame(mapping)
    if "result" in mapping or mapping.get("ok") is True:
        return parse_success_frame(mapping)
    raise ValueError("unrecognized gateway frame shape")
