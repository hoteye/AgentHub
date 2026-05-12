from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


class ErrorCodes:
    NOT_LINKED = "NOT_LINKED"
    NOT_PAIRED = "NOT_PAIRED"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAVAILABLE = "UNAVAILABLE"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    METHOD_NOT_FOUND = "METHOD_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return (
            cls.NOT_LINKED,
            cls.NOT_PAIRED,
            cls.AGENT_TIMEOUT,
            cls.INVALID_REQUEST,
            cls.UNAVAILABLE,
            cls.UNAUTHORIZED,
            cls.FORBIDDEN,
            cls.METHOD_NOT_FOUND,
            cls.INTERNAL_ERROR,
        )


@dataclass(slots=True, frozen=True)
class ErrorShape:
    code: str
    message: str
    details: Any | None = None
    retryable: bool = False
    retry_after_ms: int | None = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if self.details is None:
            payload.pop("details", None)
        if self.retry_after_ms is None:
            payload.pop("retry_after_ms", None)
        if not self.retryable:
            payload.pop("retryable", None)
        return payload


def error_shape(
    code: str,
    message: str,
    *,
    details: Any | None = None,
    retryable: bool = False,
    retry_after_ms: int | None = None,
) -> ErrorShape:
    normalized_code = str(code or "").strip().upper()
    if normalized_code not in ErrorCodes.values():
        raise ValueError(f"unknown gateway error code: {code}")
    normalized_message = str(message or "").strip()
    if not normalized_message:
        raise ValueError("error message is required")
    normalized_retry_after = int(retry_after_ms) if retry_after_ms is not None else None
    if normalized_retry_after is not None and normalized_retry_after < 0:
        raise ValueError("retry_after_ms must be non-negative")
    return ErrorShape(
        code=normalized_code,
        message=normalized_message,
        details=details,
        retryable=bool(retryable),
        retry_after_ms=normalized_retry_after,
    )


class GatewayProtocolError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Any | None = None,
        retryable: bool = False,
        retry_after_ms: int | None = None,
    ) -> None:
        self.error = error_shape(
            code,
            message,
            details=details,
            retryable=retryable,
            retry_after_ms=retry_after_ms,
        )
        super().__init__(self.error.message)

    @property
    def code(self) -> str:
        return self.error.code

    @property
    def details(self) -> Any | None:
        return self.error.details

    def to_error_shape(self) -> ErrorShape:
        return self.error

    def to_dict(self) -> Dict[str, Any]:
        return self.error.to_dict()
