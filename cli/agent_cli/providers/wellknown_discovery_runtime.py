from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

HttpClient = Callable[..., Mapping[str, Any]]

_MIN_TTL_SECONDS = 60


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_discovery_url(*, issuer: str, metadata_url: str) -> str:
    direct = _as_str(metadata_url)
    if direct:
        return direct
    normalized_issuer = _as_str(issuer).rstrip("/")
    if not normalized_issuer:
        return ""
    return f"{normalized_issuer}/.well-known/openid-configuration"


def _cache_key(*, issuer: str, metadata_url: str) -> str:
    if _as_str(metadata_url):
        return f"metadata_url::{_as_str(metadata_url)}"
    return f"issuer::{_as_str(issuer).rstrip('/')}"


def _default_http_client(
    *,
    method: str,
    url: str,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: int = 8,
) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={str(k): str(v) for k, v in (headers or {}).items()},
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(request, timeout=max(1, int(timeout_seconds or 8))) as response:
            return {
                "status_code": int(getattr(response, "status", 200) or 200),
                "body": response.read().decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return {
            "status_code": int(getattr(exc, "code", 0) or 0),
            "body": body,
            "error": f"http_{int(getattr(exc, 'code', 0) or 0)}",
        }
    except Exception as exc:
        return {"error": f"network:{str(exc)}"}


def _read_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": {}}
    if not isinstance(payload, dict):
        return {"entries": {}}
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        payload["entries"] = {}
    return payload


def _write_cache(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_fields(payload: Mapping[str, Any], *, issuer: str, metadata_url: str) -> Dict[str, Any]:
    return {
        "issuer": _as_str(payload.get("issuer")) or _as_str(issuer),
        "token_endpoint": _as_str(payload.get("token_endpoint")),
        "device_authorization_endpoint": _as_str(payload.get("device_authorization_endpoint")),
        "authorization_endpoint": _as_str(payload.get("authorization_endpoint")),
        "metadata_url": _as_str(metadata_url),
    }


def discover_wellknown_metadata(
    *,
    cache_path: Path,
    issuer: str = "",
    metadata_url: str = "",
    ttl_seconds: int = 3600,
    timeout_seconds: int = 8,
    now_ts: float | None = None,
    http_client: HttpClient | None = None,
) -> Dict[str, Any]:
    resolved_metadata_url = _to_discovery_url(issuer=issuer, metadata_url=metadata_url)
    if not resolved_metadata_url:
        return {"status": "error", "error": "missing_issuer_or_metadata_url"}
    now = int(now_ts if now_ts is not None else time.time())
    ttl = max(_MIN_TTL_SECONDS, int(ttl_seconds or 0))
    key = _cache_key(issuer=issuer, metadata_url=metadata_url)

    cache_payload = _read_cache(cache_path)
    entries = cache_payload.setdefault("entries", {})
    cached_entry = entries.get(key) if isinstance(entries, dict) else None
    if not isinstance(cached_entry, dict):
        cached_entry = {}

    client = http_client or _default_http_client
    remote = client(
        method="GET",
        url=resolved_metadata_url,
        headers={"Accept": "application/json"},
        timeout_seconds=timeout_seconds,
    )
    remote_error = _as_str(remote.get("error")) if isinstance(remote, Mapping) else "invalid_http_client_response"
    if isinstance(remote, Mapping) and not remote_error:
        status_code = _to_int(remote.get("status_code"), 0)
        body_text = _as_str(remote.get("body"))
        if 200 <= status_code < 300:
            try:
                parsed = json.loads(body_text) if body_text else {}
            except Exception:
                parsed = None
            if isinstance(parsed, Mapping):
                fields = _extract_fields(parsed, issuer=issuer, metadata_url=resolved_metadata_url)
                entry = {
                    "fetched_at": now,
                    "expires_at": now + ttl,
                    "issuer": fields["issuer"],
                    "token_endpoint": fields["token_endpoint"],
                    "device_authorization_endpoint": fields["device_authorization_endpoint"],
                    "authorization_endpoint": fields["authorization_endpoint"],
                    "metadata_url": resolved_metadata_url,
                }
                entries[key] = entry
                _write_cache(cache_path, cache_payload)
                return {"status": "ok", **entry}
            remote_error = "invalid_metadata_payload"
        else:
            remote_error = f"http_{status_code or 'error'}"

    cached_expires_at = _to_int(cached_entry.get("expires_at"), 0)
    if cached_entry and cached_expires_at > now:
        return {
            "status": "fallback_cached",
            "fetched_at": _to_int(cached_entry.get("fetched_at"), 0),
            "expires_at": cached_expires_at,
            "issuer": _as_str(cached_entry.get("issuer")),
            "token_endpoint": _as_str(cached_entry.get("token_endpoint")),
            "device_authorization_endpoint": _as_str(cached_entry.get("device_authorization_endpoint")),
            "authorization_endpoint": _as_str(cached_entry.get("authorization_endpoint")),
            "metadata_url": _as_str(cached_entry.get("metadata_url")) or resolved_metadata_url,
            "error": remote_error or "remote_fetch_failed",
        }

    return {"status": "error", "error": remote_error or "remote_fetch_failed"}
