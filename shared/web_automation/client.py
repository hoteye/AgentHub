from __future__ import annotations

from urllib.parse import urlparse

from shared.web_automation.service import BrowserService
from shared.web_automation.types import (
    BrowserArtifact,
    BrowserConsoleEntry,
    BrowserSnapshot,
    BrowserTab,
)


_service = BrowserService()


def replace_service(service: BrowserService | None = None) -> BrowserService:
    global _service
    previous = _service
    next_service = service if service is not None else BrowserService()
    if previous is not next_service:
        try:
            previous.shutdown()
        except Exception:
            pass
    _service = next_service
    return _service


class BrowserClient:
    pass


def _tab_payload(action: str, tab: BrowserTab | None, *, profile: str | None, url: str | None) -> dict[str, object]:
    if tab is None:
        return {"ok": False, "action": action, "profile": profile or _service.state.default_profile, "url": url}
    return {
        "ok": True,
        "action": action,
        "profile": tab.profile,
        "target_id": tab.tab_id,
        "url": tab.url,
        "title": tab.title,
    }


def _snapshot_payload(
    action: str,
    snapshot: BrowserSnapshot | None,
    *,
    profile: str | None,
    target_id: str | None,
) -> dict[str, object]:
    if snapshot is None:
        return {
            "ok": False,
            "action": action,
            "profile": profile or _service.state.default_profile,
            "target_id": target_id,
        }
    return {
        "ok": True,
        "action": action,
        "profile": profile or _service.state.default_profile,
        "target_id": snapshot.target_id,
        "url": snapshot.url,
        "title": snapshot.title,
        "text": snapshot.text,
        "refs": [
            {"ref": ref.ref, "role": ref.role, "name": ref.name, "url": ref.url}
            for ref in snapshot.refs
        ],
        "truncated": snapshot.truncated,
    }


def _console_payload(
    action: str,
    entries: list[BrowserConsoleEntry] | None,
    *,
    profile: str | None,
    target_id: str | None,
) -> dict[str, object]:
    resolved_target = _resolve_client_target_id(tab_id=target_id, profile=profile)
    if entries is None:
        return {
            "ok": False,
            "action": action,
            "profile": profile or _service.state.default_profile,
            "target_id": resolved_target,
        }
    messages = []
    levels: dict[str, int] = {}
    for entry in entries:
        payload: dict[str, object] = {
            "level": entry.type,
            "message": entry.text,
            "timestamp": entry.timestamp,
        }
        if entry.location:
            payload["location"] = dict(entry.location)
        messages.append(payload)
        levels[entry.type] = levels.get(entry.type, 0) + 1
    return {
        "ok": True,
        "action": action,
        "profile": profile or _service.state.default_profile,
        "target_id": resolved_target,
        "count": len(entries),
        "entries": messages,
        "messages": messages,
        "levels": levels,
    }


def _artifact_payload(
    action: str,
    artifact: BrowserArtifact | None,
    *,
    profile: str | None,
    target_id: str | None,
) -> dict[str, object]:
    if artifact is None:
        return {
            "ok": False,
            "action": action,
            "profile": profile or _service.state.default_profile,
            "target_id": target_id,
        }
    return {
        "ok": True,
        "action": action,
        "profile": profile or _service.state.default_profile,
        "target_id": artifact.target_id,
        "artifact": {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind,
            "path": artifact.path,
            "content_type": artifact.content_type,
            "size_bytes": artifact.size_bytes,
            "created_at": artifact.created_at,
            "url": artifact.url,
            "title": artifact.title,
            "ref": artifact.ref,
            "suggested_filename": artifact.suggested_filename,
        },
    }


def _request_payload(
    *,
    profile: str | None,
    target_id: str | None,
    entries: list[dict[str, object]] | None,
) -> dict[str, object]:
    resolved_target = _resolve_client_target_id(tab_id=target_id, profile=profile)
    if entries is None:
        return {
            "ok": False,
            "action": "requests",
            "profile": profile or _service.state.default_profile,
            "target_id": resolved_target,
        }
    normalized_entries = [dict(entry) for entry in entries]
    outcomes: dict[str, int] = {}
    for item in normalized_entries:
        outcome = str(item.get("outcome") or "").strip().lower()
        if outcome:
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {
        "ok": True,
        "action": "requests",
        "profile": profile or _service.state.default_profile,
        "target_id": resolved_target,
        "count": len(normalized_entries),
        "entries": normalized_entries,
        "outcomes": outcomes,
    }


def _resolve_client_target_id(*, tab_id: str | None, profile: str | None) -> str | None:
    if str(tab_id or "").strip():
        return str(tab_id).strip()
    tabs = _service.list_tabs(profile=profile)
    status = _service.status()
    if status.active_tab and any(tab.tab_id == status.active_tab for tab in tabs):
        return status.active_tab
    return tabs[-1].tab_id if tabs else None


def _profile_mode(spec) -> str:
    if spec is None:
        return ""
    driver = str(getattr(spec, "driver", "") or "").strip().lower()
    cdp_url = str(getattr(spec, "cdp_url", "") or "").strip()
    if driver == "existing-session":
        return "local-existing-session"
    if cdp_url:
        return "remote-cdp"
    return "local-managed"


def _profile_capabilities(spec) -> dict[str, object]:
    mode = _profile_mode(spec)
    return {
        "mode": mode,
        "is_remote": mode == "remote-cdp",
        "uses_chrome_mcp": False,
        "uses_existing_session": mode == "local-existing-session",
        "uses_persistent_playwright": bool(str(getattr(spec, "user_data_dir", "") or "").strip()),
        "supports_per_tab_ws": mode == "local-managed",
        "supports_json_tab_endpoints": mode == "local-managed",
        "supports_reset": mode == "local-managed",
        "supports_managed_tab_limit": mode == "local-managed",
        "cdp_is_loopback": _cdp_is_loopback(getattr(spec, "cdp_url", "")),
    }


def _cdp_is_loopback(raw_url: object) -> bool:
    parsed = urlparse(str(raw_url or "").strip())
    hostname = str(parsed.hostname or "").strip().lower()
    if not hostname:
        return False
    return hostname == "localhost" or hostname == "127.0.0.1" or hostname == "::1"


def _profile_transport(spec) -> str:
    mode = _profile_mode(spec)
    if mode == "local-existing-session":
        return "existing-session"
    if mode == "remote-cdp":
        return "cdp"
    if mode == "local-managed":
        return "managed"
    return ""


def _profile_spec(profile_name: str):
    for spec in _service.list_profiles():
        if str(getattr(spec, "name", "") or "") == str(profile_name or ""):
            return spec
    return None


from shared.web_automation.client_core_ops import bind_browser_client_core_ops
from shared.web_automation.client_perform_ops import bind_browser_client_perform_ops
from shared.web_automation.client_state_ops import bind_browser_client_state_ops

bind_browser_client_perform_ops(BrowserClient)
bind_browser_client_core_ops(BrowserClient)
bind_browser_client_state_ops(BrowserClient)
