from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def default_cache_path(*, cwd: str | Path | None = None) -> Path:
    root = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()
    return root / ".agent_cli" / "model_catalog_cache.json"


def read_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"providers": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"providers": {}}
    if not isinstance(payload, dict):
        return {"providers": {}}
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        payload["providers"] = {}
    return payload


def write_cache(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def provider_cache_entry(cache_payload: Dict[str, Any], provider_name: str) -> Dict[str, Any]:
    providers = cache_payload.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        cache_payload["providers"] = providers
    entry = providers.get(provider_name)
    if not isinstance(entry, dict):
        entry = {}
        providers[provider_name] = entry
    return entry


def update_provider_cache(
    cache_payload: Dict[str, Any],
    *,
    provider_name: str,
    models: List[Dict[str, Any]],
    etag: str = "",
    last_modified: str = "",
    ttl_seconds: int = 3600,
    now: float | None = None,
) -> Dict[str, Any]:
    fetched_at = int(now if now is not None else time.time())
    entry = provider_cache_entry(cache_payload, provider_name)
    entry.update(
        {
            "provider": provider_name,
            "models": list(models or []),
            "etag": str(etag or "").strip(),
            "last_modified": str(last_modified or "").strip(),
            "fetched_at": fetched_at,
            "expires_at": fetched_at + max(30, int(ttl_seconds or 0)),
        }
    )
    return entry


def cached_models(
    cache_payload: Dict[str, Any],
    *,
    provider_name: str,
) -> List[Dict[str, Any]]:
    entry = provider_cache_entry(cache_payload, provider_name)
    models = entry.get("models")
    if not isinstance(models, list):
        return []
    return [dict(item) for item in models if isinstance(item, dict)]

