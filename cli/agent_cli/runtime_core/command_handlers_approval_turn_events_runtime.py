from __future__ import annotations

from typing import Any


def _turn_item_index(item_id: Any) -> int | None:
    raw_id = str(item_id or "").strip()
    if not raw_id.startswith("item_"):
        return None
    try:
        return int(raw_id.split("_", 1)[1])
    except (TypeError, ValueError):
        return None


def _next_turn_item_index(events: list[dict[str, object]]) -> int:
    highest = -1
    for raw_event in list(events or []):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        index = _turn_item_index(item.get("id"))
        if index is not None:
            highest = max(highest, index)
    return highest + 1


def _rebase_turn_item_ids(
    events: list[dict[str, object]],
    *,
    offset: int,
) -> list[dict[str, object]]:
    if offset <= 0:
        return [dict(item) for item in list(events or []) if isinstance(item, dict)]
    rebased: list[dict[str, object]] = []
    for raw_event in list(events or []):
        if not isinstance(raw_event, dict):
            continue
        event = dict(raw_event)
        item = event.get("item")
        if isinstance(item, dict):
            projected_item = dict(item)
            index = _turn_item_index(projected_item.get("id"))
            if index is not None:
                projected_item["id"] = f"item_{index + offset}"
            event["item"] = projected_item
        rebased.append(event)
    return rebased


def _merge_approval_display_turn_events(
    *,
    approval_item_events: list[dict[str, object]],
    resumed_turn_events: list[dict[str, object]],
) -> list[dict[str, object]]:
    normalized_approval_events = [
        dict(item) for item in list(approval_item_events or []) if isinstance(item, dict)
    ]
    normalized_resumed_events = [
        dict(item) for item in list(resumed_turn_events or []) if isinstance(item, dict)
    ]
    if not normalized_resumed_events:
        return []
    if not normalized_approval_events:
        return normalized_resumed_events

    offset = _next_turn_item_index(normalized_approval_events)
    rebased_resumed_events = _rebase_turn_item_ids(
        normalized_resumed_events,
        offset=offset,
    )
    resumed_body = [
        dict(event)
        for event in rebased_resumed_events
        if str(event.get("type") or "").strip() != "turn.started"
    ]
    return [
        {"type": "turn.started"},
        *normalized_approval_events,
        *resumed_body,
    ]
