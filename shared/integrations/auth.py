from __future__ import annotations

import base64
from typing import Mapping, Optional


DEFAULT_SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "api-key",
    "cookie",
    "set-cookie",
}


def merge_headers(*header_sets: Optional[Mapping[str, object]]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for header_set in header_sets:
        if not header_set:
            continue
        for key, value in header_set.items():
            name = str(key or "").strip()
            if not name:
                continue
            merged[name] = str(value)
    return merged


def build_basic_auth_header(username: str, password: str) -> str:
    raw = f"{username}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def build_bearer_auth_headers(token: str, *, headers: Optional[Mapping[str, object]] = None) -> dict[str, str]:
    merged = merge_headers(headers)
    merged["Authorization"] = f"Bearer {str(token or '').strip()}"
    return merged


def apply_api_key_headers(
    api_key: str,
    *,
    header_name: str = "X-API-Key",
    headers: Optional[Mapping[str, object]] = None,
) -> dict[str, str]:
    merged = merge_headers(headers)
    merged[str(header_name or "X-API-Key")] = str(api_key or "")
    return merged


def redact_headers(
    headers: Optional[Mapping[str, object]],
    *,
    sensitive_names: Optional[set[str]] = None,
    placeholder: str = "***",
) -> dict[str, str]:
    redacted: dict[str, str] = {}
    sensitive = {item.lower() for item in (sensitive_names or DEFAULT_SENSITIVE_HEADERS)}
    for key, value in (headers or {}).items():
        name = str(key or "")
        if name.lower() in sensitive:
            redacted[name] = placeholder
            continue
        redacted[name] = str(value)
    return redacted
