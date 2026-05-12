from __future__ import annotations

import hashlib
import json
from typing import Any


def media_artifact_handle(payload: dict[str, Any]) -> str:
    normalized = {
        "path": str(payload.get("path") or "").strip(),
        "mime_type": str(payload.get("mime_type") or "").strip(),
        "size_bytes": int(payload.get("size_bytes") or 0),
        "width": int(payload.get("width") or 0),
        "height": int(payload.get("height") or 0),
        "image_url": str(payload.get("image_url") or "").strip(),
        "detail": str(payload.get("detail") or "").strip(),
    }
    digest = hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"img_{digest[:16]}"


def record_from_media_payload(
    payload: dict[str, Any],
    *,
    evidence: str,
    call_id: str = "",
) -> dict[str, Any]:
    handle = media_artifact_handle(payload)
    record: dict[str, Any] = {
        "handle": handle,
        "evidence": evidence,
    }
    if call_id:
        record["call_id"] = call_id
    path = str(payload.get("path") or "").strip()
    if path:
        record["path"] = path
    mime_type = str(payload.get("mime_type") or "").strip()
    if mime_type:
        record["mime_type"] = mime_type
    width = int(payload.get("width") or 0)
    if width > 0:
        record["width"] = width
    height = int(payload.get("height") or 0)
    if height > 0:
        record["height"] = height
    size_bytes = int(payload.get("size_bytes") or 0)
    if size_bytes > 0:
        record["size_bytes"] = size_bytes
    detail = str(payload.get("detail") or "").strip()
    if detail:
        record["detail"] = detail
    return record


def sorted_unique_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in list(records or []):
        key = (
            str(record.get("handle") or "").strip(),
            str(record.get("evidence") or "").strip(),
            str(record.get("call_id") or "").strip(),
        )
        if not key[0] or key in deduped:
            continue
        deduped[key] = dict(record)
    ordered_keys = sorted(deduped.keys())
    return [deduped[key] for key in ordered_keys]


def media_artifact_persistence_state(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {}
    ready_handles = sorted(
        {
            str(record.get("handle") or "").strip()
            for record in records
            if str(record.get("evidence") or "").strip() == "image_ready"
            and str(record.get("handle") or "").strip()
        }
    )
    injected_handles = sorted(
        {
            str(record.get("handle") or "").strip()
            for record in records
            if str(record.get("evidence") or "").strip() == "image_injected"
            and str(record.get("handle") or "").strip()
        }
    )
    return {
        "schema": "v1",
        "ready_handles": ready_handles,
        "injected_handles": injected_handles,
        "records": records,
    }
