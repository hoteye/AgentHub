from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

_AUTH_HTTP_STATUS_CODES = frozenset({401, 403})


@dataclass(frozen=True)
class MCPAuthConfig:
    token: str = ""
    headers: dict[str, str] = field(default_factory=dict)


def has_header(headers: Mapping[str, str] | None, name: str) -> bool:
    if not headers:
        return False
    needle = str(name or "").strip().lower()
    if not needle:
        return False
    return any(str(key).strip().lower() == needle for key in headers)


def merge_auth_headers(*, base_headers: Mapping[str, str] | None, auth: MCPAuthConfig | None) -> dict[str, str]:
    merged: dict[str, str] = {}
    if base_headers:
        merged.update({str(key): str(value) for key, value in base_headers.items()})
    if not auth:
        return merged
    # Precedence: base headers < token-derived Authorization < explicit auth.headers.
    if auth.token and not has_header(merged, "Authorization"):
        merged["Authorization"] = f"Bearer {auth.token}"
    if auth.headers:
        merged.update({str(key): str(value) for key, value in auth.headers.items()})
    return merged


def auth_config_from_server_config(config: Mapping[str, Any] | None) -> MCPAuthConfig | None:
    payload = config if isinstance(config, Mapping) else {}
    raw_auth = payload.get("auth")
    auth_mapping = raw_auth if isinstance(raw_auth, Mapping) else {}
    token = str(
        auth_mapping.get("token")
        or payload.get("auth_token")
        or payload.get("token")
        or ""
    ).strip()
    raw_headers = auth_mapping.get("headers")
    if not isinstance(raw_headers, Mapping):
        raw_headers = payload.get("auth_headers")
    headers: dict[str, str] = {}
    if isinstance(raw_headers, Mapping):
        headers = {str(key): str(value) for key, value in raw_headers.items()}
    if not token and not headers:
        return None
    return MCPAuthConfig(token=token, headers=headers)


def with_auth_config(
    *,
    config: Mapping[str, Any] | None,
    token: str,
    headers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(config or {})
    auth_payload = dict(payload.get("auth") or {}) if isinstance(payload.get("auth"), Mapping) else {}
    token_value = str(token or auth_payload.get("token") or "").strip()
    merged_headers = dict(auth_payload.get("headers") or {}) if isinstance(auth_payload.get("headers"), Mapping) else {}
    if isinstance(headers, Mapping):
        merged_headers.update({str(key): str(value) for key, value in headers.items()})
    if token_value:
        auth_payload["token"] = token_value
    if merged_headers:
        auth_payload["headers"] = merged_headers
    payload["auth"] = auth_payload
    return payload


def is_auth_status_code(status_code: int) -> bool:
    return int(status_code) in _AUTH_HTTP_STATUS_CODES
