from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def normalize_browser_requests_payload(
    payload: Dict[str, Any],
    *,
    client: Any,
    profile: str | None,
    requested_target: str | None,
    requested_url: str | None,
    browser_text_fn,
    resolve_browser_target_fn,
) -> Dict[str, Any]:
    normalized = dict(payload)
    raw_entries = payload.get("entries")
    source_entries = raw_entries if isinstance(raw_entries, list) else payload.get("requests")
    entries: List[Dict[str, Any]] = []
    outcomes: Dict[str, int] = {}
    for item in source_entries if isinstance(source_entries, list) else []:
        if not isinstance(item, dict):
            continue
        location = item.get("location")
        location_payload = dict(location) if isinstance(location, dict) else {}
        method = browser_text_fn(item.get("method") or location_payload.get("method")).upper()
        status_raw = item.get("status")
        if status_raw is None:
            status_raw = location_payload.get("status")
        try:
            status: Any = (
                int(status_raw) if status_raw is not None and str(status_raw).strip() else None
            )
        except (TypeError, ValueError):
            status = browser_text_fn(status_raw)
        resource_type = browser_text_fn(
            item.get("resource_type")
            or item.get("resource")
            or location_payload.get("resource_type")
            or location_payload.get("resource")
        )
        entry_url = browser_text_fn(item.get("url") or location_payload.get("url"))
        outcome = browser_text_fn(item.get("outcome") or location_payload.get("outcome")).lower()
        message = browser_text_fn(item.get("message") or item.get("text"))
        entry: Dict[str, Any] = {}
        if method:
            entry["method"] = method
        if status is not None and str(status).strip():
            entry["status"] = status
        if resource_type:
            entry["resource_type"] = resource_type
        if entry_url:
            entry["url"] = entry_url
        if outcome:
            entry["outcome"] = outcome
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        if message:
            entry["message"] = message
        timestamp = item.get("timestamp")
        if timestamp is not None:
            entry["timestamp"] = timestamp
        request_id = browser_text_fn(item.get("request_id") or location_payload.get("request_id"))
        if request_id:
            entry["request_id"] = request_id
        if entry:
            entries.append(entry)
    normalized["entries"] = entries
    normalized["count"] = len(entries)
    if outcomes:
        normalized["outcomes"] = outcomes
    target_id = resolve_browser_target_fn(
        payload,
        client=client,
        action="requests",
        profile=profile,
        requested_target=requested_target,
    )
    if target_id:
        normalized["target_id"] = target_id
    if not browser_text_fn(normalized.get("url")):
        normalized["url"] = (
            browser_text_fn(entries[0].get("url")) if entries else browser_text_fn(requested_url)
        )
    return normalized


def normalize_browser_artifact_payload(
    payload: Dict[str, Any],
    *,
    client: Any,
    action: str,
    profile: str | None,
    requested_target: str | None,
    requested_url: str | None,
    requested_ref: str | None,
    browser_text_fn,
    resolve_browser_target_fn,
) -> Dict[str, Any]:
    normalized = dict(payload)
    artifact = payload.get("artifact")
    artifact_payload = dict(artifact) if isinstance(artifact, dict) else {}
    target_id = resolve_browser_target_fn(
        payload,
        client=client,
        action=action,
        profile=profile,
        requested_target=requested_target,
    )
    if target_id:
        normalized["target_id"] = target_id
    if profile and not browser_text_fn(normalized.get("profile")):
        normalized["profile"] = profile
    url = (
        browser_text_fn(normalized.get("url"))
        or browser_text_fn(artifact_payload.get("url"))
        or browser_text_fn(requested_url)
    )
    if url:
        normalized["url"] = url
    path = browser_text_fn(artifact_payload.get("path"))
    if path:
        normalized["path"] = path
    if action == "pdf":
        normalized["format"] = "pdf"
    elif action == "screenshot":
        normalized["format"] = "png"
    else:
        path_value = browser_text_fn(artifact_payload.get("path"))
        suffix = Path(path_value).suffix.lower().lstrip(".") if path_value else ""
        normalized["format"] = suffix or "bin"
    size = artifact_payload.get("size_bytes")
    if size is not None:
        normalized["size"] = int(size)
    content_type = browser_text_fn(artifact_payload.get("content_type"))
    if content_type:
        normalized["content_type"] = content_type
    created_at = artifact_payload.get("created_at")
    if created_at is not None:
        normalized["created_at"] = created_at
    title = browser_text_fn(artifact_payload.get("title"))
    if title:
        normalized["title"] = title
    suggested_filename = browser_text_fn(artifact_payload.get("suggested_filename"))
    if suggested_filename:
        normalized["suggested_filename"] = suggested_filename
    if requested_ref:
        normalized["ref"] = requested_ref
    else:
        artifact_ref = browser_text_fn(artifact_payload.get("ref"))
        if artifact_ref:
            normalized["ref"] = artifact_ref
    return normalized
