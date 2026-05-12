from __future__ import annotations

from typing import Dict

from shared.web_automation.snapshot import ensure_tab_snapshot_seed
from shared.web_automation.storage import load_state, save_state
from shared.web_automation.types import (
    BrowserArtifact,
    BrowserConsoleEntry,
    BrowserDialogHook,
    BrowserPageRef,
    BrowserTab,
    BrowserUploadHook,
    ProfileState,
)


def _load_tabs(profiles: Dict[str, ProfileState]) -> None:
    saved = load_state()
    profile_payloads = saved.get("profiles") if isinstance(saved, dict) else None
    for profile_name, profile_state in profiles.items():
        raw_profile = profile_payloads.get(profile_name, {}) if isinstance(profile_payloads, dict) else {}
        if isinstance(raw_profile, dict):
            raw_tabs = raw_profile.get("tabs", [])
            active_tab = raw_profile.get("active_tab")
        else:
            raw_tabs = saved.get(profile_name, []) if isinstance(saved, dict) else []
            active_tab = None
        profile_state.tabs = [
            _deserialize_tab(profile_name, entry)
            for entry in raw_tabs
            if isinstance(entry, dict) and entry.get("tab_id")
        ]
        if profile_state.tabs:
            profile_state.active_tab = (
                active_tab
                if any(tab.tab_id == active_tab for tab in profile_state.tabs)
                else profile_state.tabs[-1].tab_id
            )


def _persist_tabs(profiles: Dict[str, ProfileState]) -> None:
    saved = load_state()
    if not isinstance(saved, dict):
        saved = {}
    saved["version"] = 2
    saved["profiles"] = {}
    profile_payloads = saved["profiles"]
    assert isinstance(profile_payloads, dict)
    for profile_name, profile_state in profiles.items():
        profile_payloads[profile_name] = {
            "active_tab": profile_state.active_tab,
            "tabs": [_serialize_tab(tab) for tab in profile_state.tabs],
        }
    save_state(saved)


def _deserialize_tab(profile_name: str, entry: dict) -> BrowserTab:
    tab = BrowserTab(
        tab_id=str(entry["tab_id"]),
        url=str(entry.get("url") or ""),
        title=str(entry.get("title") or entry.get("url") or ""),
        profile=profile_name,
        text=str(entry.get("text") or ""),
        refs=[_deserialize_ref(item) for item in entry.get("refs", []) if isinstance(item, dict)],
        console=[_deserialize_console(item) for item in entry.get("console", []) if isinstance(item, dict)],
        artifacts=[_deserialize_artifact(item) for item in entry.get("artifacts", []) if isinstance(item, dict)],
        cookies=[_deserialize_cookie(item) for item in entry.get("cookies", []) if isinstance(item, dict)],
        local_storage={
            str(key): str(value)
            for key, value in (entry.get("local_storage") or {}).items()
            if str(key).strip()
        }
        if isinstance(entry.get("local_storage"), dict)
        else {},
        session_storage={
            str(key): str(value)
            for key, value in (entry.get("session_storage") or {}).items()
            if str(key).strip()
        }
        if isinstance(entry.get("session_storage"), dict)
        else {},
        input_state={
            str(key): str(value)
            for key, value in (entry.get("input_state") or {}).items()
            if str(key).strip()
        }
        if isinstance(entry.get("input_state"), dict)
        else {},
        uploaded_files={
            str(key): [str(path) for path in value if str(path).strip()]
            for key, value in (entry.get("uploaded_files") or {}).items()
            if str(key).strip() and isinstance(value, list)
        }
        if isinstance(entry.get("uploaded_files"), dict)
        else {},
        armed_upload=_deserialize_upload_hook(entry.get("armed_upload")),
        armed_dialog=_deserialize_dialog_hook(entry.get("armed_dialog")),
        last_dialog=(str(entry.get("last_dialog")) if entry.get("last_dialog") is not None else None),
    )
    ensure_tab_snapshot_seed(tab)
    return tab


def _serialize_tab(tab: BrowserTab) -> dict[str, object]:
    return {
        "tab_id": tab.tab_id,
        "url": tab.url,
        "title": tab.title,
        "text": tab.text,
        "refs": [
            {
                "ref": ref.ref,
                "role": ref.role,
                "name": ref.name,
                "url": ref.url,
                "selector": ref.selector,
            }
            for ref in tab.refs
        ],
        "console": [
            {
                "type": entry.type,
                "text": entry.text,
                "timestamp": entry.timestamp,
                "location": entry.location,
            }
            for entry in tab.console
        ],
        "artifacts": [
            {
                "artifact_id": artifact.artifact_id,
                "kind": artifact.kind,
                "path": artifact.path,
                "content_type": artifact.content_type,
                "size_bytes": artifact.size_bytes,
                "created_at": artifact.created_at,
                "target_id": artifact.target_id,
                "url": artifact.url,
                "title": artifact.title,
                "ref": artifact.ref,
                "suggested_filename": artifact.suggested_filename,
            }
            for artifact in tab.artifacts
        ],
        "cookies": [dict(item) for item in tab.cookies],
        "local_storage": dict(tab.local_storage),
        "session_storage": dict(tab.session_storage),
        "input_state": dict(tab.input_state),
        "uploaded_files": {ref: list(paths) for ref, paths in tab.uploaded_files.items()},
        "armed_upload": _serialize_upload_hook(tab.armed_upload),
        "armed_dialog": _serialize_dialog_hook(tab.armed_dialog),
        "last_dialog": tab.last_dialog,
    }


def _deserialize_ref(entry: dict) -> BrowserPageRef:
    return BrowserPageRef(
        ref=str(entry.get("ref") or ""),
        role=str(entry.get("role") or "link"),
        name=(str(entry["name"]) if entry.get("name") is not None else None),
        url=(str(entry["url"]) if entry.get("url") is not None else None),
        selector=(str(entry["selector"]) if entry.get("selector") is not None else None),
    )


def _deserialize_console(entry: dict) -> BrowserConsoleEntry:
    location = entry.get("location")
    return BrowserConsoleEntry(
        type=str(entry.get("type") or "info"),
        text=str(entry.get("text") or ""),
        timestamp=str(entry.get("timestamp") or ""),
        location=(dict(location) if isinstance(location, dict) else None),
    )


def _deserialize_artifact(entry: dict) -> BrowserArtifact:
    return BrowserArtifact(
        artifact_id=str(entry.get("artifact_id") or ""),
        kind=str(entry.get("kind") or ""),
        path=str(entry.get("path") or ""),
        content_type=str(entry.get("content_type") or "application/octet-stream"),
        size_bytes=int(entry.get("size_bytes") or 0),
        created_at=str(entry.get("created_at") or ""),
        target_id=str(entry.get("target_id") or ""),
        url=str(entry.get("url") or ""),
        title=str(entry.get("title") or ""),
        ref=(str(entry.get("ref")) if entry.get("ref") is not None else None),
        suggested_filename=(
            str(entry.get("suggested_filename")) if entry.get("suggested_filename") is not None else None
        ),
    )


def _deserialize_cookie(entry: dict) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": str(entry.get("name") or ""),
        "value": str(entry.get("value") or ""),
        "domain": str(entry.get("domain") or ""),
        "path": str(entry.get("path") or "/"),
        "httpOnly": bool(entry.get("httpOnly")),
        "secure": bool(entry.get("secure")),
        "sameSite": str(entry.get("sameSite") or ""),
    }
    if entry.get("expires") is not None:
        payload["expires"] = entry.get("expires")
    return payload


def _deserialize_upload_hook(entry: object) -> BrowserUploadHook | None:
    if not isinstance(entry, dict):
        return None
    paths = [str(item) for item in entry.get("paths", []) if str(item).strip()]
    if not paths:
        return None
    return BrowserUploadHook(
        paths=paths,
        ref=(str(entry.get("ref")) if entry.get("ref") is not None else None),
        input_ref=(str(entry.get("input_ref")) if entry.get("input_ref") is not None else None),
        timeout_ms=(int(entry["timeout_ms"]) if entry.get("timeout_ms") is not None else None),
    )


def _serialize_upload_hook(hook: BrowserUploadHook | None) -> dict[str, object] | None:
    if hook is None:
        return None
    return {
        "paths": list(hook.paths),
        "ref": hook.ref,
        "input_ref": hook.input_ref,
        "timeout_ms": hook.timeout_ms,
    }


def _deserialize_dialog_hook(entry: object) -> BrowserDialogHook | None:
    if not isinstance(entry, dict):
        return None
    accept = entry.get("accept")
    if accept is None:
        return None
    return BrowserDialogHook(
        accept=bool(accept),
        prompt_text=(str(entry.get("prompt_text")) if entry.get("prompt_text") is not None else None),
        timeout_ms=(int(entry["timeout_ms"]) if entry.get("timeout_ms") is not None else None),
    )


def _serialize_dialog_hook(hook: BrowserDialogHook | None) -> dict[str, object] | None:
    if hook is None:
        return None
    return {
        "accept": hook.accept,
        "prompt_text": hook.prompt_text,
        "timeout_ms": hook.timeout_ms,
    }

