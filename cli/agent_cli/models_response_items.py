from __future__ import annotations

from typing import Any

from cli.agent_cli.models import PromptResponse, ResponseInputItem
from cli.agent_cli.models_turn_events import (
    _rebase_turn_item_events,
    _response_item_to_turn_item,
    _turn_event_content_types,
    _turn_event_usage_int,
    completed_todo_list_turn_events,
    tool_events_to_turn_events,
)


def _terminal_state_payload(
    *,
    protocol_diagnostics: dict[str, Any] | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostics = dict(protocol_diagnostics or {})
    payload = dict(diagnostics.get("turn_terminal_state") or {})
    if payload:
        return payload
    normalized_status = dict(status or {})
    terminal_state = str(normalized_status.get("terminal_state") or "").strip().lower()
    if terminal_state != "failed":
        return {}
    message = str(normalized_status.get("error") or "").strip()
    return {
        "result": terminal_state,
        "error_message": message or "turn failed",
    }


def terminal_failure_message(
    *,
    protocol_diagnostics: dict[str, Any] | None = None,
    status: dict[str, Any] | None = None,
) -> str:
    payload = _terminal_state_payload(
        protocol_diagnostics=protocol_diagnostics,
        status=status,
    )
    if str(payload.get("result") or "").strip().lower() != "failed":
        return ""
    for key in ("error_message", "message", "detail"):
        text = str(payload.get(key) or "").strip()
        if text:
            return text
    return "turn failed"


def response_message_item(
    role: str,
    text: str,
    *,
    phase: str | None = None,
) -> ResponseInputItem | None:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return None
    extra: dict[str, Any] = {}
    if phase:
        extra["phase"] = str(phase)
    return ResponseInputItem(
        item_type="message",
        role=str(role or "assistant").strip() or "assistant",
        content=[{"type": "output_text", "text": normalized_text}],
        extra=extra,
    )


def default_response_items(
    *,
    commentary_text: str = "",
    assistant_text: str = "",
) -> list[ResponseInputItem]:
    items: list[ResponseInputItem] = []
    commentary_item = response_message_item("assistant", commentary_text, phase="commentary")
    if commentary_item is not None:
        items.append(commentary_item)
    final_item = response_message_item("assistant", assistant_text, phase="final_answer")
    if final_item is not None:
        items.append(final_item)
    return items


def response_item_text(item: ResponseInputItem, *, include_reasoning: bool = True) -> str:
    content = item.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for entry in content:
            if not isinstance(entry, dict):
                continue
            entry_type = str(entry.get("type") or "").strip()
            if entry_type in {"input_text", "output_text", "text"} or (
                include_reasoning and entry_type == "reasoning"
            ):
                text = str(entry.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(content, dict):
        return str(content.get("text") or "").strip()
    if (
        include_reasoning
        and str(getattr(item, "item_type", "") or "").strip().lower() == "reasoning"
    ):
        summary = dict(getattr(item, "extra", {}) or {}).get("summary")
        if isinstance(summary, list):
            parts = [
                str(entry.get("text") or "").strip()
                for entry in summary
                if isinstance(entry, dict) and str(entry.get("text") or "").strip()
            ]
            if parts:
                return "\n\n".join(parts).strip()
    return ""


def response_items_phase_text(
    items: list[ResponseInputItem | dict[str, Any]],
    *,
    phase: str,
) -> str:
    normalized_phase = str(phase or "").strip().lower()
    if not normalized_phase:
        return ""
    for raw_item in list(items or []):
        if isinstance(raw_item, ResponseInputItem):
            item = raw_item
        elif isinstance(raw_item, dict):
            item = ResponseInputItem.from_dict(dict(raw_item))
        else:
            continue
        if str((item.extra or {}).get("phase") or "").strip().lower() != normalized_phase:
            continue
        text = response_item_text(item)
        if text:
            return text
    return ""


def response_items_to_text(
    items: list[ResponseInputItem],
    *,
    include_reasoning: bool = False,
) -> str:
    parts = [
        response_item_text(item, include_reasoning=include_reasoning) for item in list(items or [])
    ]
    return "\n\n".join([part for part in parts if part])


def _completed_agent_message_texts(events: list[dict[str, Any]]) -> set[str]:
    texts: set[str] = set()
    for event in list(events or []):
        if not isinstance(event, dict):
            continue
        if str(event.get("type") or "").strip() != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "agent_message":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            texts.add(text)
    return texts


def _events_include_agent_message(events: list[dict[str, Any]]) -> bool:
    for event in list(events or []):
        if not isinstance(event, dict):
            continue
        if str(event.get("type") or "").strip() != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() == "agent_message":
            return True
    return False


def _next_existing_item_index(events: list[dict[str, Any]]) -> int:
    next_index = 0
    for event in list(events or []):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id.startswith("item_"):
            continue
        try:
            next_index = max(next_index, int(item_id.split("_", 1)[1]) + 1)
        except ValueError:
            continue
    return next_index


def _agent_message_event_from_response(
    response: PromptResponse, *, item_id: str
) -> dict[str, Any] | None:
    visible_text = (
        str(getattr(response, "command_display_text", "") or "").strip()
        or str(getattr(response, "assistant_text", "") or "").strip()
    )
    response_items = list(getattr(response, "response_items", []) or [])
    final_text = response_items_phase_text(response_items, phase="final_answer")
    message_item = response_message_item(
        "assistant", final_text or visible_text, phase="final_answer"
    )
    if message_item is None:
        return None
    item = _response_item_to_turn_item(message_item, item_id=item_id)
    if item is None:
        return None
    return {"type": "item.completed", "item": item}


def _backfill_missing_agent_message_event(
    response: PromptResponse,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_events = [dict(item) for item in list(events or []) if isinstance(item, dict)]
    if _events_include_agent_message(normalized_events):
        return normalized_events
    message_event = _agent_message_event_from_response(
        response,
        item_id=f"item_{_next_existing_item_index(normalized_events)}",
    )
    if message_event is None:
        return normalized_events
    terminal_index = next(
        (
            index
            for index, event in enumerate(normalized_events)
            if str(event.get("type") or "").strip() in {"turn.completed", "turn.failed"}
        ),
        len(normalized_events),
    )
    return [
        *normalized_events[:terminal_index],
        message_event,
        *normalized_events[terminal_index:],
    ]


def _is_duplicate_agent_message_response_item(
    response_item: ResponseInputItem,
    *,
    completed_agent_message_texts: set[str],
) -> bool:
    if not completed_agent_message_texts:
        return False
    item_type = str(getattr(response_item, "item_type", "") or "").strip().lower()
    role = str(getattr(response_item, "role", "") or "").strip().lower()
    if item_type != "message" and role != "assistant":
        return False
    text = response_item_text(response_item, include_reasoning=False)
    return bool(text and text in completed_agent_message_texts)


def compose_turn_events_from_response_items(
    *,
    assistant_text: str,
    response_items: list[ResponseInputItem],
    executed_item_events: list[dict[str, Any]] | None = None,
    usage: dict[str, Any] | None = None,
    protocol_diagnostics: dict[str, Any] | None = None,
    status: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    normalized_item_events = [
        dict(item) for item in list(executed_item_events or []) if isinstance(item, dict)
    ]
    pre_response_items: list[ResponseInputItem] = []
    post_response_items: list[ResponseInputItem] = []
    for response_item in list(response_items or []):
        phase = str((response_item.extra or {}).get("phase") or "").strip().lower()
        content_types = _turn_event_content_types(getattr(response_item, "content", None))
        is_reasoning = (
            str(getattr(response_item, "item_type", "") or "").strip().lower() == "reasoning"
            or "reasoning" in content_types
        )
        if normalized_item_events and phase not in {"", "commentary"} and not is_reasoning:
            post_response_items.append(response_item)
        elif normalized_item_events and phase == "" and not is_reasoning:
            post_response_items.append(response_item)
        else:
            pre_response_items.append(response_item)

    events: list[dict[str, Any]] = [{"type": "turn.started"}]
    item_counter = 0
    for response_item in pre_response_items:
        item = _response_item_to_turn_item(response_item, item_id=f"item_{item_counter}")
        if item is None:
            continue
        events.append({"type": "item.completed", "item": item})
        item_counter += 1

    rebased_item_events, item_counter = _rebase_turn_item_events(
        normalized_item_events,
        start_index=item_counter,
    )
    events.extend(rebased_item_events)
    completed_agent_texts = _completed_agent_message_texts(rebased_item_events)

    for response_item in post_response_items:
        if _is_duplicate_agent_message_response_item(
            response_item,
            completed_agent_message_texts=completed_agent_texts,
        ):
            continue
        item = _response_item_to_turn_item(response_item, item_id=f"item_{item_counter}")
        if item is None:
            continue
        events.append({"type": "item.completed", "item": item})
        item_counter += 1

    events.extend(completed_todo_list_turn_events(rebased_item_events))

    normalized_usage = dict(usage or {})
    failure_message = terminal_failure_message(
        protocol_diagnostics=protocol_diagnostics,
        status=status,
    )
    if failure_message:
        events.append(
            {
                "type": "turn.failed",
                "error": {"message": failure_message},
            }
        )
    else:
        events.append(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": _turn_event_usage_int(normalized_usage.get("input_tokens")),
                    "cached_input_tokens": _turn_event_usage_int(
                        normalized_usage.get("cached_input_tokens")
                    ),
                    "output_tokens": _turn_event_usage_int(normalized_usage.get("output_tokens")),
                },
            }
        )
    return events


def prompt_response_turn_events(response: PromptResponse) -> list[dict[str, Any]]:
    if response.turn_events:
        return _backfill_missing_agent_message_event(
            response,
            [dict(item) for item in list(response.turn_events or []) if isinstance(item, dict)],
        )
    assistant_text = str(response.assistant_text or "")
    visible_assistant_text = (
        str(getattr(response, "command_display_text", "") or "").strip() or assistant_text
    )
    response_items = list(
        response.response_items
        or default_response_items(
            commentary_text=str(response.commentary_text or ""),
            assistant_text=visible_assistant_text,
        )
    )
    tool_item_events, _ = tool_events_to_turn_events(
        list(response.tool_events or []), start_index=0
    )
    return compose_turn_events_from_response_items(
        assistant_text=visible_assistant_text,
        response_items=response_items,
        executed_item_events=tool_item_events,
        usage={
            "input_tokens": (response.status or {}).get("input_tokens"),
            "cached_input_tokens": (response.status or {}).get("cached_input_tokens"),
            "output_tokens": (response.status or {}).get("output_tokens"),
        },
        protocol_diagnostics=dict(response.protocol_diagnostics or {}),
        status=dict(response.status or {}),
    )
