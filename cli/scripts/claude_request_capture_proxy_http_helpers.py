from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import SplitResult


_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _header_items(headers: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for name, value in list(headers.items()):
        items.append({"name": str(name), "value": str(value)})
    return items


def _decode_body(body: bytes) -> tuple[str | None, Any | None]:
    if not body:
        return "", None
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return None, None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    return text, payload


def _join_upstream_path(base: SplitResult, request_path: str) -> str:
    base_path = str(base.path or "").rstrip("/")
    req_path = str(request_path or "").strip()
    if not req_path.startswith("/"):
        req_path = "/" + req_path
    if not base_path:
        return req_path
    return base_path + req_path


def _upstream_target_url(base: SplitResult, path: str, query: str) -> str:
    prefix = f"{base.scheme}://{base.netloc}"
    if query:
        return f"{prefix}{path}?{query}"
    return f"{prefix}{path}"
