from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, TypeAlias

from .errors import ErrorShape

PROTOCOL_VERSION = "v1"


def _copy_map(value: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return dict(value or {})


@dataclass(slots=True, frozen=True)
class RequestFrame:
    protocol_version: str
    request_id: str
    method: str
    params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class SuccessFrame:
    protocol_version: str
    request_id: str
    ok: bool
    result: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class ErrorFrame:
    protocol_version: str
    request_id: str
    ok: bool
    error: ErrorShape
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["error"] = self.error.to_dict()
        return payload


@dataclass(slots=True, frozen=True)
class EventFrame:
    protocol_version: str
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


GatewayFrame: TypeAlias = RequestFrame | SuccessFrame | ErrorFrame | EventFrame


def request_frame(
    *,
    request_id: str,
    method: str,
    params: Dict[str, Any] | None = None,
    metadata: Dict[str, Any] | None = None,
) -> RequestFrame:
    normalized_request_id = str(request_id or "").strip()
    normalized_method = str(method or "").strip()
    if not normalized_request_id:
        raise ValueError("request_id is required")
    if not normalized_method:
        raise ValueError("method is required")
    return RequestFrame(
        protocol_version=PROTOCOL_VERSION,
        request_id=normalized_request_id,
        method=normalized_method,
        params=_copy_map(params),
        metadata=_copy_map(metadata),
    )


def success_frame(
    *,
    request_id: str,
    result: Dict[str, Any] | None = None,
    metadata: Dict[str, Any] | None = None,
) -> SuccessFrame:
    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        raise ValueError("request_id is required")
    return SuccessFrame(
        protocol_version=PROTOCOL_VERSION,
        request_id=normalized_request_id,
        ok=True,
        result=_copy_map(result),
        metadata=_copy_map(metadata),
    )


def error_frame(
    *,
    request_id: str,
    error: ErrorShape,
    metadata: Dict[str, Any] | None = None,
) -> ErrorFrame:
    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        raise ValueError("request_id is required")
    return ErrorFrame(
        protocol_version=PROTOCOL_VERSION,
        request_id=normalized_request_id,
        ok=False,
        error=error,
        metadata=_copy_map(metadata),
    )


def event_frame(
    *,
    event_type: str,
    data: Dict[str, Any] | None = None,
    metadata: Dict[str, Any] | None = None,
) -> EventFrame:
    normalized_event_type = str(event_type or "").strip()
    if not normalized_event_type:
        raise ValueError("event_type is required")
    return EventFrame(
        protocol_version=PROTOCOL_VERSION,
        event_type=normalized_event_type,
        data=_copy_map(data),
        metadata=_copy_map(metadata),
    )
