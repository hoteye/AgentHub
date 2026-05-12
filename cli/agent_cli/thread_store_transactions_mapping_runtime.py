from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List


_COMPACTED_RESERVED_METADATA_KEYS = {
    "type",
    "thread_id",
    "timestamp",
    "replacement_history",
    "message",
}


def _normalized_compacted_replacement_history(
    replacement_history: List[Dict[str, Any]] | None,
    *,
    history_item_from_rollout_payload_fn: Callable[[Dict[str, Any]], Dict[str, str] | None],
) -> List[Dict[str, str]]:
    normalized_replacement_history: List[Dict[str, str]] = []
    if replacement_history is None:
        return normalized_replacement_history
    for item in list(replacement_history):
        if not isinstance(item, dict):
            raise ValueError("invalid compacted replacement history")
        normalized = history_item_from_rollout_payload_fn(item)
        if normalized is None:
            raise ValueError("invalid compacted replacement history")
        normalized_replacement_history.append(normalized)
    return normalized_replacement_history


def _filtered_compacted_metadata(metadata: Dict[str, Any] | None) -> Dict[str, Any]:
    filtered: Dict[str, Any] = {}
    for raw_key, value in dict(metadata or {}).items():
        key = str(raw_key or "").strip()
        if not key or key in _COMPACTED_RESERVED_METADATA_KEYS:
            continue
        filtered[key] = value
    return filtered


def compacted_payload(
    *,
    thread_id: str,
    timestamp: str,
    replacement_history: List[Dict[str, Any]] | None,
    message: str,
    metadata: Dict[str, Any] | None,
    history_item_from_rollout_payload_fn: Callable[[Dict[str, Any]], Dict[str, str] | None],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "type": "compacted",
        "thread_id": thread_id,
        "timestamp": timestamp,
    }
    normalized_replacement_history = _normalized_compacted_replacement_history(
        replacement_history,
        history_item_from_rollout_payload_fn=history_item_from_rollout_payload_fn,
    )
    if replacement_history is not None:
        payload["replacement_history"] = normalized_replacement_history
    compact_message = str(message or "").strip()
    if compact_message:
        payload["message"] = compact_message
    extra_metadata = _filtered_compacted_metadata(metadata)
    if extra_metadata:
        payload.update(extra_metadata)
    return payload


def thread_meta_record_kwargs(
    *,
    rollout_item: Any,
    raw_payload: Dict[str, Any],
    utc_now_fn: Callable[[], str],
    cwd_default: str,
    rollout_path: Path,
    path_mtime_iso_fn: Callable[[Path], str],
) -> Dict[str, Any]:
    thread_id = str(
        rollout_item.thread_id
        or raw_payload.get("thread_id")
        or rollout_item.payload.get("thread_id")
        or ""
    ).strip()
    if not thread_id:
        raise ValueError(f"rollout thread_meta missing thread_id: {rollout_path}")
    created_at = (
        str(rollout_item.payload.get("created_at") or rollout_item.timestamp or "").strip()
        or utc_now_fn()
    )
    name = str(rollout_item.payload.get("name") or "").strip()
    if not name:
        name = f"Thread {created_at[:19].replace('T', ' ')}".strip()
    cwd = str(rollout_item.payload.get("cwd") or "").strip() or cwd_default
    return {
        "thread_id": thread_id,
        "name": name,
        "created_at": created_at,
        "updated_at": path_mtime_iso_fn(rollout_path),
        "rollout_path": str(rollout_path),
        "cwd": cwd,
        "turn_count": 0,
    }


def rollout_summary_from_item(
    *,
    rollout_item: Any,
    history_item_from_rollout_payload_fn: Callable[[Dict[str, Any]], Dict[str, str] | None],
) -> str:
    if rollout_item.item_type == "turn" and rollout_item.turn is not None:
        return str(rollout_item.turn.user_text or "").strip()
    if rollout_item.item_type == "compacted":
        for item in list(rollout_item.payload.get("replacement_history") or []):
            if not isinstance(item, dict):
                continue
            history_item = history_item_from_rollout_payload_fn(item)
            if history_item is None:
                continue
            return history_item["content"]
        return str(rollout_item.payload.get("message") or "").strip()
    if rollout_item.item_type != "response_item":
        return ""
    if str(rollout_item.payload.get("scope") or "").strip() == "turn_context":
        return ""
    history_item = history_item_from_rollout_payload_fn(rollout_item.payload)
    if history_item is not None and history_item["role"] == "user":
        return history_item["content"]
    return ""
