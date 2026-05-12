from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import request

from cli.agent_cli import __version__


DEFAULT_CHECK_INTERVAL_SECONDS = 20 * 60 * 60
UPDATE_CACHE_FILENAME = "version.json"


def agenthub_home() -> Path:
    return Path(os.environ.get("AGENT_CLI_HOME") or (Path.home() / ".agent_cli")).expanduser()


def update_cache_path() -> Path:
    configured = str(os.environ.get("AGENTHUB_UPDATE_CACHE_PATH") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return agenthub_home() / UPDATE_CACHE_FILENAME


def update_latest_url() -> str:
    return str(
        os.environ.get("AGENTHUB_UPDATE_LATEST_URL")
        or os.environ.get("AGENTHUB_UPDATE_MANIFEST_URL")
        or ""
    ).strip()


def current_version() -> str:
    return str(__version__ or "0.0.0").strip()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def read_update_cache(path: Path | None = None) -> dict[str, Any]:
    return _read_json(path or update_cache_path())


def write_update_cache(payload: dict[str, Any], path: Path | None = None) -> Path:
    target = path or update_cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return target


def normalize_release_version(value: Any) -> str:
    text = str(value or "").strip()
    for prefix in ("cli-v", "agenthub-v", "v"):
        if text.lower().startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def _parse_semver(value: Any) -> tuple[int, int, int] | None:
    text = normalize_release_version(value)
    parts = text.split(".")
    if len(parts) != 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def is_newer_version(latest: Any, current: Any) -> bool:
    latest_version = _parse_semver(latest)
    current_version_value = _parse_semver(current)
    return bool(latest_version is not None and current_version_value is not None and latest_version > current_version_value)


def _extract_latest_version(payload: dict[str, Any]) -> str:
    for key in ("latest_version", "version", "tag_name", "name"):
        version = normalize_release_version(payload.get(key))
        if _parse_semver(version) is not None:
            return version
    return ""


def fetch_latest_version(url: str, *, timeout_seconds: float = 5.0) -> str:
    req = request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": f"AgentHub/{current_version()}",
        },
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        raw = response.read()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("latest version response must be a JSON object")
    latest = _extract_latest_version(dict(payload))
    if not latest:
        raise RuntimeError("latest version response did not contain a semver version")
    return latest


def _checked_at_from_cache(cache: dict[str, Any]) -> datetime | None:
    text = str(cache.get("last_checked_at") or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def cache_is_stale(cache: dict[str, Any], *, now: datetime | None = None, interval_seconds: int = DEFAULT_CHECK_INTERVAL_SECONDS) -> bool:
    checked_at = _checked_at_from_cache(cache)
    if checked_at is None:
        return True
    return checked_at < (now or _utc_now()) - timedelta(seconds=interval_seconds)


def refresh_update_cache(*, url: str | None = None, cache_path: Path | None = None) -> dict[str, Any]:
    source_url = str(url or update_latest_url()).strip()
    if not source_url:
        raise RuntimeError("update latest URL is not configured")
    latest = fetch_latest_version(source_url)
    previous = read_update_cache(cache_path)
    payload = {
        "latest_version": latest,
        "last_checked_at": _utc_now().isoformat(),
        "source_url": source_url,
        "dismissed_version": str(previous.get("dismissed_version") or "").strip(),
    }
    write_update_cache(payload, cache_path)
    return payload


def schedule_background_update_check() -> bool:
    source_url = update_latest_url()
    if not source_url:
        return False
    cache = read_update_cache()
    if not cache_is_stale(cache):
        return False

    def _worker() -> None:
        try:
            refresh_update_cache(url=source_url)
        except Exception:
            return

    threading.Thread(target=_worker, name="agenthub-update-check", daemon=True).start()
    return True


def dismiss_cached_update(*, cache_path: Path | None = None) -> dict[str, Any]:
    cache = read_update_cache(cache_path)
    latest = normalize_release_version(cache.get("latest_version"))
    if latest:
        cache["dismissed_version"] = latest
        write_update_cache(cache, cache_path)
    return cache


def cached_update_notice() -> str:
    if not update_latest_url():
        return ""
    cache = read_update_cache()
    latest = normalize_release_version(cache.get("latest_version"))
    if not latest:
        return ""
    if str(cache.get("dismissed_version") or "").strip() == latest:
        return ""
    current = current_version()
    if not is_newer_version(latest, current):
        return ""
    return f"AgentHub update available: {current} -> {latest}. Run /update status."


def update_status_lines(*, refresh: bool = False) -> list[str]:
    source_url = update_latest_url()
    cache_path = update_cache_path()
    refresh_error = ""
    if refresh:
        try:
            cache = refresh_update_cache(url=source_url, cache_path=cache_path)
        except Exception as exc:
            cache = read_update_cache(cache_path)
            refresh_error = str(exc)
    else:
        cache = read_update_cache(cache_path)
    latest = normalize_release_version(cache.get("latest_version")) or "-"
    current = current_version()
    update_available = latest != "-" and is_newer_version(latest, current)
    lines = [
        "update status",
        f"current_version={current}",
        f"latest_version={latest}",
        f"update_available={'true' if update_available else 'false'}",
        f"check_enabled={'true' if bool(source_url) else 'false'}",
        f"check_url={source_url or '-'}",
        f"cache_path={cache_path}",
        f"last_checked_at={str(cache.get('last_checked_at') or '-')}",
        f"dismissed_version={str(cache.get('dismissed_version') or '-')}",
    ]
    if refresh:
        lines.append(f"refresh_error={refresh_error or '-'}")
    if update_available:
        lines.append("next_action=download the latest release asset for your platform")
    elif not source_url:
        lines.append("next_action=set AGENTHUB_UPDATE_LATEST_URL after publishing GitHub releases")
    else:
        lines.append("next_action=none")
    return lines


def update_status_text(*, refresh: bool = False) -> str:
    return "\n".join(update_status_lines(refresh=refresh))


__all__ = [
    "cached_update_notice",
    "cache_is_stale",
    "current_version",
    "dismiss_cached_update",
    "fetch_latest_version",
    "is_newer_version",
    "normalize_release_version",
    "read_update_cache",
    "refresh_update_cache",
    "schedule_background_update_check",
    "update_cache_path",
    "update_latest_url",
    "update_status_text",
    "write_update_cache",
]
