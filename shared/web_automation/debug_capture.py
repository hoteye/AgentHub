from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.web_automation.artifacts import create_artifact_path, record_artifact, resolve_artifact_output_path
from shared.web_automation.snapshot import build_snapshot
from shared.web_automation.types import BrowserArtifact, BrowserTab


def start_capture_session(
    *,
    profile: str,
    target_id: str | None,
    url: str | None,
    title: str | None,
    mode: str,
) -> dict[str, Any]:
    return {
        "trace_id": f"trace_{uuid.uuid4().hex[:12]}",
        "profile": str(profile or "").strip(),
        "target_id": str(target_id or "").strip() or None,
        "url": str(url or "").strip() or None,
        "title": str(title or "").strip() or None,
        "mode": str(mode or "debug_bundle").strip() or "debug_bundle",
        "started_at": _timestamp(),
        "status": "active",
    }


def emit_debug_capture_artifact(
    tab: BrowserTab,
    *,
    session: dict[str, Any],
    cookies: list[dict[str, Any]] | None = None,
    storage_state: dict[str, Any] | None = None,
    requested_path: str | None = None,
    max_chars: int = 4000,
    max_refs: int = 50,
) -> BrowserArtifact:
    capture_path = _capture_output_path(tab, session=session, requested_path=requested_path)
    snapshot = build_snapshot(tab, max_chars=max_chars, max_refs=max_refs)
    payload = {
        "trace_id": session.get("trace_id"),
        "profile": tab.profile,
        "target_id": tab.tab_id,
        "url": tab.url,
        "title": tab.title,
        "mode": session.get("mode") or "debug_bundle",
        "started_at": session.get("started_at"),
        "stopped_at": _timestamp(),
        "snapshot": {
            "target_id": snapshot.target_id,
            "url": snapshot.url,
            "title": snapshot.title,
            "text": snapshot.text,
            "truncated": snapshot.truncated,
            "refs": [
                {"ref": item.ref, "role": item.role, "name": item.name, "url": item.url}
                for item in snapshot.refs
            ],
        },
        "console": [
            {
                "type": entry.type,
                "text": entry.text,
                "timestamp": entry.timestamp,
                "location": dict(entry.location) if entry.location else None,
            }
            for entry in tab.console
        ],
        "cookies": [dict(item) for item in list(cookies or [])],
        "storage_state": dict(storage_state or {"origins": []}),
        "artifacts": [
            {
                "artifact_id": artifact.artifact_id,
                "kind": artifact.kind,
                "path": artifact.path,
                "content_type": artifact.content_type,
                "size_bytes": artifact.size_bytes,
                "created_at": artifact.created_at,
                "ref": artifact.ref,
                "suggested_filename": artifact.suggested_filename,
            }
            for artifact in tab.artifacts[-20:]
        ],
    }
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    capture_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return record_artifact(
        tab,
        kind="trace",
        path=capture_path,
        content_type="application/json",
        size_bytes=capture_path.stat().st_size,
        url=tab.url,
        title=tab.title,
        suggested_filename=capture_path.name,
    )


def _capture_output_path(
    tab: BrowserTab,
    *,
    session: dict[str, Any],
    requested_path: str | None,
) -> Path:
    if str(requested_path or "").strip():
        return resolve_artifact_output_path("traces", str(requested_path))
    trace_id = str(session.get("trace_id") or uuid.uuid4().hex[:12]).strip() or uuid.uuid4().hex[:12]
    return create_artifact_path("traces", f"{tab.tab_id}-{trace_id}.json")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
