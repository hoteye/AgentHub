from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in items:
        item = str(raw or "").strip()
        if not item or item in seen:
            continue
        ordered.append(item)
        seen.add(item)
    return ordered


def _response_tool_names(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in list(payload.get("response_items") or []):
        if str(item.get("type") or "").strip() != "function_call":
            continue
        names.append(str(item.get("name") or ""))
    return _dedupe(names)


def _canonical_tool_names(payload: dict[str, Any]) -> list[str]:
    names = [str((event or {}).get("name") or "") for event in list(payload.get("tool_events") or [])]
    return _dedupe(names)


def _projected_tool_names(payload: dict[str, Any]) -> list[str]:
    names = list(_response_tool_names(payload))
    for event in list(payload.get("tool_events") or []):
        event_payload = dict((event or {}).get("payload") or {})
        names.append(str(event_payload.get("function_call_name") or ""))
    return _dedupe(names)


def _assistant_text(payload: dict[str, Any]) -> str:
    return str(payload.get("assistant_text") or "").strip()


def _tool_event(payload: dict[str, Any], name: str) -> dict[str, Any] | None:
    target = str(name or "").strip()
    for event in list(payload.get("tool_events") or []):
        if str((event or {}).get("name") or "").strip() == target:
            return dict(event or {})
    return None


def _turn_item_types(payload: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for event in list(payload.get("turn_events") or []):
        item = dict((event or {}).get("item") or {})
        items.append(str(item.get("type") or ""))
    return _dedupe(items)


def _validation_result(status: str, summary: str, notes: Sequence[str], details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "summary": str(summary or "").strip(),
        "notes": [str(note).strip() for note in notes if str(note or "").strip()],
        "details": dict(details or {}),
    }


def _temp_path(run: dict[str, Any], relative: str) -> Path:
    return Path(str(run.get("workspace") or "")) / relative
