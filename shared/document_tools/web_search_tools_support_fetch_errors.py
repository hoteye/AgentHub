from __future__ import annotations

import html
import socket
import ssl
from typing import Any
from urllib.error import HTTPError, URLError

_NETWORK_UNREACHABLE_ERRNOS = {
    -2,
    -3,
    8,
    101,
    11001,
    11004,
    10051,
    10065,
    113,
}
_NETWORK_UNREACHABLE_TEXT = (
    "network is unreachable",
    "no route to host",
    "temporary failure in name resolution",
    "name or service not known",
    "nodename nor servname provided",
    "getaddrinfo failed",
    "host is down",
)
_FETCH_FALLBACK_HINT = "Direct page fetch failed; use web_search/native search snippets or another accessible source when available."


def _clean_error_text(value: str) -> str:
    return " ".join(html.unescape(str(value or "")).split()).strip()


def _read_exception_body(exc: BaseException, *, limit: int = 1200) -> str:
    reader = getattr(exc, "read", None)
    if not callable(reader):
        return ""
    try:
        data = reader(limit)
    except Exception:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", "ignore").strip()
    return str(data or "").strip()


def _header_value(headers: Any, name: str) -> str:
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return ""
    for candidate in (name, name.lower(), name.title()):
        try:
            value = getter(candidate)
        except Exception:
            value = None
        if value is not None:
            return str(value or "").strip()
    return ""


def _exception_reason(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    if reason is None:
        return ""
    return str(reason or "").strip()


def _classify_fetch_failure(exc: BaseException, *, body_preview: str = "") -> str:
    reason = _exception_reason(exc)
    combined = " ".join(
        part
        for part in [
            type(exc).__name__,
            str(exc),
            reason,
            body_preview,
        ]
        if part
    ).lower()
    if isinstance(exc, HTTPError):
        headers = getattr(exc, "headers", None)
        cf_mitigated = _header_value(headers, "cf-mitigated").lower()
        server = _header_value(headers, "server").lower()
        if cf_mitigated == "challenge" or ("cloudflare" in server and "challenge" in combined):
            return "cloudflare_challenge"
        status_code = int(getattr(exc, "code", 0) or 0)
        if status_code == 403:
            return "http_403"
        if status_code == 401:
            return "http_401"
        if status_code == 429:
            return "http_429"
        if status_code == 451:
            return "http_451"
        if status_code >= 400:
            return f"http_{status_code}"
        return "http_error"
    reason_obj = getattr(exc, "reason", None)
    if isinstance(exc, URLError):
        if (
            isinstance(reason_obj, ssl.SSLEOFError)
            or "unexpected_eof" in combined
            or "eof occurred" in combined
        ):
            return "tls_eof"
        if isinstance(reason_obj, TimeoutError | socket.timeout) or "timed out" in combined:
            return "timeout"
        if any(token in combined for token in _NETWORK_UNREACHABLE_TEXT):
            return "network_unreachable"
        return "url_error"
    if (
        isinstance(exc, ssl.SSLEOFError)
        or "unexpected_eof" in combined
        or "eof occurred" in combined
    ):
        return "tls_eof"
    if isinstance(exc, TimeoutError | socket.timeout) or "timed out" in combined:
        return "timeout"
    return "fetch_failed"


def _web_fetch_failure_payload(exc: BaseException) -> dict[str, Any]:
    body_preview = _clean_error_text(_read_exception_body(exc))[:500]
    headers = getattr(exc, "headers", None)
    blocked_reason = _classify_fetch_failure(exc, body_preview=body_preview)
    raw_error = f"{type(exc).__name__}: {exc}"
    payload: dict[str, Any] = {
        "error": f"{raw_error} (blocked_reason={blocked_reason})",
        "error_type": type(exc).__name__,
        "blocked_reason": blocked_reason,
        "fallback_hint": _FETCH_FALLBACK_HINT,
    }
    reason = _exception_reason(exc)
    if reason:
        payload["reason"] = reason
    status_code = getattr(exc, "code", None)
    if status_code is not None:
        payload["status_code"] = int(status_code)
    final_url = ""
    get_url = getattr(exc, "geturl", None)
    if callable(get_url):
        try:
            final_url = str(get_url() or "").strip()
        except Exception:
            final_url = ""
    if not final_url:
        final_url = str(getattr(exc, "url", "") or "").strip()
    if final_url:
        payload["final_url"] = final_url
    server = _header_value(headers, "server")
    if server:
        payload["server"] = server
    cf_mitigated = _header_value(headers, "cf-mitigated")
    if cf_mitigated:
        payload["cf_mitigated"] = cf_mitigated
    if body_preview:
        payload["body_preview"] = body_preview
    return payload
