from __future__ import annotations

from shared.web_automation.types import (
    BrowserArtifact,
    BrowserConsoleEntry,
    BrowserPageRef,
    BrowserTab,
)


def project_artifact(artifact: BrowserArtifact) -> dict[str, object]:
    return {
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
    }


def project_request_entries(
    entries: list[BrowserConsoleEntry],
    *,
    fallback_url: str,
) -> list[dict[str, object]]:
    return [_project_request_entry(entry, fallback_url=fallback_url) for entry in entries]


def project_highlight_result(
    *,
    tab: BrowserTab,
    target_ref: BrowserPageRef,
    normalized_ref: str,
    mode: str,
    duration_ms: int,
    artifact: BrowserArtifact,
) -> dict[str, object]:
    return {
        "ok": True,
        "action": "highlight",
        "target_id": tab.tab_id,
        "profile": tab.profile,
        "url": tab.url,
        "title": tab.title,
        "ref": normalized_ref,
        "role": target_ref.role,
        "name": target_ref.name,
        "highlight_mode": mode,
        "duration_ms": duration_ms,
        "artifact": project_artifact(artifact),
    }


def project_trace_start_reused_result(
    *,
    tab: BrowserTab,
    session: dict[str, object],
) -> dict[str, object]:
    return {
        "ok": True,
        "action": "trace_start",
        "profile": tab.profile,
        "target_id": tab.tab_id,
        "trace_id": session.get("trace_id"),
        "capture_mode": session.get("mode") or "debug_bundle",
        "status": "active",
        "reused": True,
    }


def project_trace_start_result(
    *,
    tab: BrowserTab,
    session: dict[str, object],
    mode: str,
) -> dict[str, object]:
    return {
        "ok": True,
        "action": "trace_start",
        "profile": tab.profile,
        "target_id": tab.tab_id,
        "trace_id": session["trace_id"],
        "capture_mode": mode,
        "started_at": session["started_at"],
        "status": "active",
    }


def project_trace_stop_result(
    *,
    tab: BrowserTab,
    session: dict[str, object],
    capture_mode: str,
    artifact: BrowserArtifact,
) -> dict[str, object]:
    return {
        "ok": True,
        "action": "trace_stop",
        "profile": tab.profile,
        "target_id": tab.tab_id,
        "trace_id": session["trace_id"],
        "capture_mode": capture_mode,
        "artifact": project_artifact(artifact),
    }


def _project_request_entry(
    entry: BrowserConsoleEntry,
    *,
    fallback_url: str,
) -> dict[str, object]:
    location = dict(entry.location or {})
    status_value = location.get("status")
    try:
        status: int | str | None = int(status_value) if status_value is not None else None
    except (TypeError, ValueError):
        status = str(status_value) if status_value is not None else None
    payload: dict[str, object] = {
        "method": str(location.get("method") or "").strip().upper(),
        "status": status,
        "resource_type": str(
            location.get("resource_type") or location.get("resource") or ""
        ).strip(),
        "url": str(location.get("url") or fallback_url or "").strip(),
        "outcome": str(location.get("outcome") or "").strip().lower(),
        "message": entry.text,
        "timestamp": entry.timestamp,
    }
    request_id = str(location.get("request_id") or "").strip()
    if request_id:
        payload["request_id"] = request_id
    return payload
