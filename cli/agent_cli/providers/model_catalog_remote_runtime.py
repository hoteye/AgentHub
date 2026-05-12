from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict

from cli.agent_cli.providers import model_catalog_cache_runtime as cache_runtime


def _extract_models(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        models = payload.get("models")
        if isinstance(models, list):
            return [dict(item) for item in models if isinstance(item, dict)]
    return []


def fetch_remote_catalog(
    *,
    catalog_endpoint: str,
    etag: str = "",
    last_modified: str = "",
    timeout_seconds: int = 8,
) -> Dict[str, Any]:
    headers = {"Accept": "application/json"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    request = urllib.request.Request(catalog_endpoint, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=max(1, int(timeout_seconds or 8))) as response:
            body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(body) if body.strip() else {}
            return {
                "status": "ok",
                "models": _extract_models(payload),
                "etag": str(response.headers.get("ETag") or "").strip(),
                "last_modified": str(response.headers.get("Last-Modified") or "").strip(),
            }
    except urllib.error.HTTPError as exc:
        if int(getattr(exc, "code", 0) or 0) == 304:
            return {"status": "not_modified"}
        return {"status": "error", "error": f"http_{getattr(exc, 'code', 'error')}"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def refresh_provider_catalog_cache(
    *,
    cache_path: Path,
    provider_name: str,
    catalog_endpoint: str,
    ttl_seconds: int = 3600,
    force: bool = False,
) -> Dict[str, Any]:
    now = int(time.time())
    cache_payload = cache_runtime.read_cache(cache_path)
    current_entry = cache_runtime.provider_cache_entry(cache_payload, provider_name)
    expires_at = int(current_entry.get("expires_at") or 0)
    if not force and expires_at > now and isinstance(current_entry.get("models"), list):
        return {
            "status": "cached",
            "models": cache_runtime.cached_models(cache_payload, provider_name=provider_name),
            "cache_hit": True,
        }

    remote = fetch_remote_catalog(
        catalog_endpoint=catalog_endpoint,
        etag=str(current_entry.get("etag") or "").strip(),
        last_modified=str(current_entry.get("last_modified") or "").strip(),
    )
    status = str(remote.get("status") or "")
    if status == "ok":
        cache_runtime.update_provider_cache(
            cache_payload,
            provider_name=provider_name,
            models=list(remote.get("models") or []),
            etag=str(remote.get("etag") or "").strip(),
            last_modified=str(remote.get("last_modified") or "").strip(),
            ttl_seconds=ttl_seconds,
            now=float(now),
        )
        cache_runtime.write_cache(cache_path, cache_payload)
        return {
            "status": "refreshed",
            "models": cache_runtime.cached_models(cache_payload, provider_name=provider_name),
            "cache_hit": False,
        }
    if status == "not_modified":
        cache_runtime.update_provider_cache(
            cache_payload,
            provider_name=provider_name,
            models=cache_runtime.cached_models(cache_payload, provider_name=provider_name),
            etag=str(current_entry.get("etag") or "").strip(),
            last_modified=str(current_entry.get("last_modified") or "").strip(),
            ttl_seconds=ttl_seconds,
            now=float(now),
        )
        cache_runtime.write_cache(cache_path, cache_payload)
        return {
            "status": "not_modified",
            "models": cache_runtime.cached_models(cache_payload, provider_name=provider_name),
            "cache_hit": True,
        }

    return {
        "status": "fallback_cached",
        "error": str(remote.get("error") or "remote_fetch_failed"),
        "models": cache_runtime.cached_models(cache_payload, provider_name=provider_name),
        "cache_hit": True,
    }

