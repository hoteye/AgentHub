from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult

DEFAULT_PROMPT = (
    "Use the lookup_constant tool exactly once with key alpha. "
    "Do not answer before the tool returns. "
    "After the tool returns, answer with exactly alpha and nothing else."
)
DEFAULT_EXPECTED_OUTPUT = "alpha"

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
_REJECTION_BODY = {
    "error": {
        "message": "Unsupported parameter: previous_response_id",
        "type": "invalid_request_error",
        "param": "previous_response_id",
        "code": "unsupported_parameter",
    }
}


@dataclass(frozen=True)
class ProxyConfig:
    upstream_base_url: str
    out_dir: Path
    upstream_timeout_seconds: float = 180.0


@dataclass(frozen=True)
class ObservedRequest:
    sequence: int
    method: str
    path: str
    query: str
    previous_response_id: str
    input_types: list[str]
    tool_names: list[str]
    injected_rejection: bool
    forwarded_url: str


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _default_out_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="previous_response_id_live_")).resolve()


def _redacted_headers(headers: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for name, value in list(headers.items()):
        lowered = str(name or "").strip().lower()
        text = str(value or "")
        if lowered in {"authorization", "x-api-key", "api-key"}:
            text = "<redacted>"
        items.append({"name": str(name), "value": text})
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


def _body_item_types(payload: Any) -> list[str]:
    result: list[str] = []
    items = payload.get("input") if isinstance(payload, dict) else None
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type:
            result.append(item_type)
            continue
        role = str(item.get("role") or "").strip()
        if role:
            result.append(f"message:{role}")
    return result


def _tool_names(payload: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(payload, dict):
        return names
    for item in list(payload.get("tools") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
