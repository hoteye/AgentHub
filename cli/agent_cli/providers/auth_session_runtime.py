from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

_VALID_STATUSES = {"ready", "expired", "missing", "invalid"}


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:  # NaN
        return None
    return parsed


@dataclass(frozen=True)
class AuthSession:
    provider_name: str
    token_ref: str
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = ""
    scope: str = ""
    expires_at: Optional[float] = None
    issued_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "provider_name": self.provider_name,
            "token_ref": self.token_ref,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "scope": self.scope,
            "expires_at": self.expires_at,
            "issued_at": self.issued_at,
            "metadata": dict(self.metadata),
        }
        return payload

    @staticmethod
    def from_mapping(payload: Mapping[str, Any]) -> "AuthSession":
        return AuthSession(
            provider_name=_as_str(payload.get("provider_name")),
            token_ref=_as_str(payload.get("token_ref")),
            access_token=_as_str(payload.get("access_token")),
            refresh_token=_as_str(payload.get("refresh_token")),
            token_type=_as_str(payload.get("token_type")),
            scope=_as_str(payload.get("scope")),
            expires_at=_as_float(payload.get("expires_at")),
            issued_at=_as_float(payload.get("issued_at")),
            metadata=dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), Mapping) else {},
        )


def auth_session_status(
    session: AuthSession | None,
    *,
    now_ts: float | None = None,
    expiry_skew_seconds: int = 30,
) -> str:
    if session is None:
        return "missing"
    if _as_str(session.provider_name) == "" or _as_str(session.token_ref) == "":
        return "invalid"
    if not session.access_token and not session.refresh_token:
        return "missing"
    if session.expires_at is None:
        return "ready" if bool(session.access_token) else "missing"
    if session.expires_at <= 0:
        return "invalid"
    now_value = float(now_ts if now_ts is not None else time.time())
    if session.expires_at <= (now_value + max(0, int(expiry_skew_seconds))):
        return "expired"
    return "ready"


def ensure_auth_session_status(value: str) -> str:
    normalized = _as_str(value).lower()
    if normalized in _VALID_STATUSES:
        return normalized
    return "invalid"

