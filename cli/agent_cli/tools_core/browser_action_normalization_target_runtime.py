from __future__ import annotations

from typing import Any


TARGETED_BROWSER_ACTIONS = {
    "snapshot",
    "console",
    "errors",
    "requests",
    "screenshot",
    "pdf",
    "download",
    "wait_download",
    "highlight",
    "trace_start",
    "trace_stop",
    "cookies",
    "cookies_get",
    "cookies_set",
    "cookies_clear",
    "storage_state",
    "storage_get",
    "storage_set",
    "storage_clear",
    "act",
}


def resolve_browser_target(
    payload: dict[str, Any],
    *,
    client: Any,
    action: str,
    profile: str | None,
    requested_target: str | None,
    browser_text_fn: Any,
) -> str | None:
    direct_target = browser_text_fn(payload.get("target_id"))
    if direct_target:
        return direct_target
    artifact = payload.get("artifact")
    if isinstance(artifact, dict):
        artifact_target = browser_text_fn(artifact.get("target_id"))
        if artifact_target:
            return artifact_target
    if requested_target:
        return requested_target
    if action not in TARGETED_BROWSER_ACTIONS:
        return None
    try:
        if profile:
            tabs = client.tabs(profile=profile)
            return tabs[-1].tab_id if tabs else None
        status = client.status()
        if status.active_tab:
            return status.active_tab
        tabs = client.tabs(profile=profile)
        return tabs[-1].tab_id if tabs else None
    except Exception:
        return None
