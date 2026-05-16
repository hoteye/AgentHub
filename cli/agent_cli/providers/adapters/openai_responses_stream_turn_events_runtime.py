from __future__ import annotations

from typing import Any

from cli.agent_cli.models import ResponseInputItem, response_item_text
from cli.agent_cli.models_turn_events_runtime import native_web_search_turn_item_from_response_item
from cli.agent_cli.providers.adapters.openai_responses_output import _stream_item_to_dict


def is_terminal_stream_response(response: Any) -> bool:
    if response is None:
        return False
    status = str(getattr(response, "status", "") or "").strip().lower()
    if status in {"completed", "incomplete", "failed"}:
        return True
    if str(getattr(response, "id", "") or "").strip():
        if bool(list(getattr(response, "output", []) or [])):
            return True
        if str(getattr(response, "output_text", "") or "").strip():
            return True
    return False


def native_web_search_started_event(event: Any) -> dict[str, Any] | None:
    raw_item = _stream_item_to_dict(getattr(event, "item", None))
    if not isinstance(raw_item, dict):
        return None
    if str(raw_item.get("type") or "").strip() != "web_search_call":
        return None
    action = raw_item.get("action")
    query_text = ""
    if isinstance(action, dict):
        query_text = str(action.get("query") or "").strip()
        if not query_text:
            queries = action.get("queries")
            if isinstance(queries, list):
                for entry in queries:
                    text = str(entry or "").strip()
                    if text:
                        query_text = text
                        break
    item_id = str(
        raw_item.get("id") or f"stream_web_search_{getattr(event, 'output_index', 0)}"
    ).strip()
    item: dict[str, Any] = {
        "id": item_id,
        "type": "web_search_call",
        "status": "in_progress",
        "search_phase": "search_dispatched",
    }
    if isinstance(action, dict):
        item["action"] = dict(action)
    if query_text:
        item["query"] = query_text
    return {"type": "item.started", "item": item}


def response_item_turn_event(item: ResponseInputItem, *, item_id: str) -> dict[str, Any] | None:
    item_type = str(getattr(item, "item_type", "") or "").strip().lower()
    content = getattr(item, "content", None)
    content_types = (
        {
            str(entry.get("type") or "").strip().lower()
            for entry in list(content or [])
            if isinstance(entry, dict)
        }
        if isinstance(content, list)
        else set()
    )
    text = response_item_text(item).strip()
    if item_type == "reasoning" or "reasoning" in content_types:
        if not text:
            return None
        extra = dict(getattr(item, "extra", {}) or {})
        event_item: dict[str, Any] = {
            "id": item_id,
            "type": "reasoning",
            "text": text,
        }
        for key in ("status", "summary", "encrypted_content"):
            value = extra.get(key)
            if value not in (None, ""):
                event_item[key] = value
        provider_item_id = str(extra.get("id") or "").strip()
        if provider_item_id:
            event_item["provider_item_id"] = provider_item_id
        return {
            "type": "item.completed",
            "item": event_item,
        }
    if item_type == "web_search_call":
        return {
            "type": "item.completed",
            "item": native_web_search_turn_item_from_response_item(
                item,
                item_id=item_id,
                search_phase="search_results_received",
            ),
        }
    if (
        item_type == "message"
        or str(getattr(item, "role", "") or "").strip().lower() == "assistant"
    ):
        if not text:
            return None
        event_item: dict[str, Any] = {
            "id": item_id,
            "type": "agent_message",
            "text": text,
        }
        phase = str((getattr(item, "extra", {}) or {}).get("phase") or "").strip().lower()
        if phase:
            event_item["phase"] = phase
        return {
            "type": "item.completed",
            "item": event_item,
        }
    return None


__all__ = [
    "is_terminal_stream_response",
    "native_web_search_started_event",
    "response_item_turn_event",
]
