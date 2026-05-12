from __future__ import annotations

from urllib.parse import urlparse

from shared.web_automation.types import BrowserTab


def _normalize_storage_kind(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"local", "session"}:
        return normalized
    raise ValueError("storage_kind must be one of: local, session")


def _origin_for_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _normalize_cookie(cookie: dict[str, object], *, tab: BrowserTab) -> dict[str, object]:
    name = str(cookie.get("name") or "").strip()
    value = str(cookie.get("value") or "")
    if not name:
        raise ValueError("cookies must include cookie name")
    domain = str(cookie.get("domain") or "").strip()
    path = str(cookie.get("path") or "/").strip() or "/"
    same_site = str(cookie.get("sameSite") or "").strip()
    origin = _origin_for_url(tab.url)
    normalized: dict[str, object] = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "httpOnly": bool(cookie.get("httpOnly")),
        "secure": bool(cookie.get("secure")),
        "sameSite": same_site,
    }
    if not domain and origin:
        normalized["url"] = origin
    if cookie.get("expires") is not None:
        normalized["expires"] = cookie.get("expires")
    return normalized


def _cookie_identity(cookie: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(cookie.get("name") or "").strip(),
        str(cookie.get("domain") or cookie.get("url") or "").strip(),
        str(cookie.get("path") or "/").strip() or "/",
    )

