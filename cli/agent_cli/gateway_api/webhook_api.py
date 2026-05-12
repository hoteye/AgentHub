from __future__ import annotations

import json
from typing import Any, Dict, Optional

from cli.agent_cli.gateway_core import GatewayEvent, create_gateway_event
from shared.integrations import DEFAULT_SENSITIVE_HEADERS, verify_hmac_sha256_hex


_SENSITIVE_HEADER_FRAGMENTS = (
    "token",
    "signature",
    "secret",
    "auth",
    "cookie",
)
_REDACTED = "***"


def build_webhook_event(
    *,
    connector_key: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    source_id: str = "webhook",
    correlation_id: str | None = None,
) -> GatewayEvent:
    return create_gateway_event(
        event_type=event_type,
        source_kind="webhook",
        source_id=source_id,
        connector_key=connector_key,
        correlation_id=correlation_id,
        payload=dict(payload or {}),
        metadata={"headers": sanitize_webhook_headers(headers)},
    )


def parse_webhook_body(raw_body: str | bytes) -> Dict[str, Any]:
    text = raw_body.decode("utf-8") if isinstance(raw_body, bytes) else str(raw_body)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("rawBody must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("rawBody must decode to a JSON object")
    return dict(payload)


def sanitize_webhook_headers(headers: Optional[Dict[str, Any]]) -> Dict[str, str]:
    sanitized: Dict[str, str] = {}
    for key, value in (headers or {}).items():
        name = str(key or "").strip()
        if not name:
            continue
        lowered = name.lower()
        text = str(value)
        if lowered in DEFAULT_SENSITIVE_HEADERS or any(fragment in lowered for fragment in _SENSITIVE_HEADER_FRAGMENTS):
            sanitized[name] = _REDACTED
            continue
        sanitized[name] = text
    return sanitized


def find_header_value(headers: Optional[Dict[str, Any]], name: str) -> Optional[str]:
    expected = str(name or "").strip().lower()
    if not expected:
        return None
    for key, value in (headers or {}).items():
        if str(key or "").strip().lower() == expected:
            return str(value)
    return None


def verify_webhook_signature(
    *,
    headers: Optional[Dict[str, Any]],
    raw_body: str | bytes,
    secret: str,
    header_name: str = "X-Hub-Signature-256",
    prefix: str = "sha256=",
) -> bool:
    provided = find_header_value(headers, header_name)
    if not provided:
        return False
    return verify_hmac_sha256_hex(secret, raw_body, provided, prefix=prefix)
