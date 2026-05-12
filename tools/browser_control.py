from __future__ import annotations

from typing import Dict, List

from shared.web_automation.client import BrowserClient

_client = BrowserClient()


def status() -> Dict[str, object]:
    status = _client.status()
    return {
        "running": status.running,
        "active_profile": status.active_profile,
        "active_tab": status.active_tab,
        "profile_count": status.profile_count,
    }


def start(profile: str | None = None) -> Dict[str, object]:
    return {"ok": _client.start(profile)}


def stop(profile: str | None = None) -> Dict[str, object]:
    return {"ok": _client.stop(profile)}


def profiles() -> List[str]:
    return _client.profiles()


def tabs(profile: str | None = None) -> List[Dict[str, str]]:
    return [
        {"tab_id": tab.tab_id, "url": tab.url, "title": tab.title, "profile": tab.profile}
        for tab in _client.tabs(profile=profile)
    ]


def open_tab(url: str, profile: str | None = None) -> Dict[str, str]:
    tab = _client.open(url=url, profile=profile)
    if not tab:
        return {"error": "browser unavailable"}
    return {"tab_id": tab.tab_id, "url": tab.url, "title": tab.title, "profile": tab.profile}


def focus(tab_id: str, profile: str | None = None) -> Dict[str, object]:
    return {"ok": _client.focus(tab_id=tab_id, profile=profile)}


def close(tab_id: str, profile: str | None = None) -> Dict[str, object]:
    return {"ok": _client.close(tab_id=tab_id, profile=profile)}


def navigate(url: str, profile: str | None = None) -> Dict[str, str]:
    tab = _client.navigate(url=url, profile=profile)
    if not tab:
        return {"error": "navigation failed"}
    return {"tab_id": tab.tab_id, "url": tab.url, "title": tab.title}
