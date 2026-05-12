from __future__ import annotations

from typing import Any, Callable


def bounded_turn_segment_tail(
    segments: list[list[dict[str, Any]]],
    *,
    planner_history_limit: int,
) -> list[dict[str, Any]]:
    selected: list[list[dict[str, Any]]] = []
    selected_count = 0
    for raw_segment in reversed(list(segments or [])):
        segment = [dict(item) for item in list(raw_segment or []) if isinstance(item, dict)]
        if not segment:
            continue
        if not selected:
            selected.append(segment)
            selected_count += len(segment)
            continue
        if selected_count + len(segment) > planner_history_limit:
            break
        selected.append(segment)
        selected_count += len(segment)
    flattened: list[dict[str, Any]] = []
    for segment in reversed(selected):
        flattened.extend(segment)
    return flattened


def history_item_from_rollout_payload(payload: dict[str, Any]) -> dict[str, str] | None:
    item = payload.get("item")
    if isinstance(item, dict):
        payload = item
    role = str(payload.get("role") or "").strip().lower()
    content = payload.get("content")
    if isinstance(content, list):
        text_parts = [
            str(entry.get("text") or "")
            for entry in content
            if isinstance(entry, dict) and str(entry.get("text") or "").strip()
        ]
        content_text = "\n".join(part for part in text_parts if part)
    else:
        content_text = str(payload.get("text") or content or "").strip()
    if role not in {"user", "assistant", "system", "developer"} or not content_text:
        return None
    return {"role": role, "content": content_text}


def response_input_item_from_rollout_payload(
    payload: dict[str, Any],
    *,
    response_input_item_from_dict_fn: Callable[[dict[str, Any]], Any],
) -> dict[str, Any] | None:
    item = payload.get("item")
    source = item if isinstance(item, dict) else payload
    if not isinstance(source, dict) or not source:
        return None
    normalized = response_input_item_from_dict_fn(source).to_dict()
    if not normalized:
        return None
    if (
        str(normalized.get("type") or "").strip() == "message"
        and not str(normalized.get("role") or "").strip()
        and "content" not in normalized
    ):
        return None
    return normalized


def history_item_from_planner_input_item(payload: dict[str, Any], *, history_item_from_rollout_payload_fn) -> dict[str, str] | None:
    item = dict(payload or {})
    if str(item.get("type") or "").strip() not in {"", "message"}:
        return None
    return history_item_from_rollout_payload_fn(item)


def reference_context_item_from_rollout_payload(
    payload: dict[str, Any],
    *,
    reference_context_item_from_dict_fn: Callable[[dict[str, Any]], Any],
) -> Any | None:
    item = payload.get("item")
    source = item if isinstance(item, dict) else payload
    if not isinstance(source, dict):
        return None
    return reference_context_item_from_dict_fn(source)


def state_snapshot_from_rollout_payload(payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = payload.get("state")
    if isinstance(snapshot, dict):
        return dict(snapshot)
    return {key: value for key, value in payload.items() if key != "item"}


def rollback_turn_count(payload: dict[str, Any]) -> int:
    raw = payload.get("num_turns")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def compacted_replacement_history(
    payload: dict[str, Any],
    *,
    existing_history: list[dict[str, str]] | None,
    history_item_from_rollout_payload_fn,
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for item in list(payload.get("replacement_history") or []):
        if not isinstance(item, dict):
            continue
        normalized = history_item_from_rollout_payload_fn(item)
        if normalized is not None:
            history.append(normalized)
    if history:
        return history
    summary = str(payload.get("message") or "").strip()
    if not summary:
        return []
    for item in list(existing_history or []):
        if str(item.get("role") or "").strip().lower() != "user":
            continue
        content = str(item.get("content") or "").strip()
        if content:
            history.append({"role": "user", "content": content})
    history.append({"role": "user", "content": summary})
    return history


def history_from_turns(turns: list[Any], *, preferred_assistant_turn_text_fn) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for turn in turns:
        user_text = str(turn.user_text or "")
        assistant_text = preferred_assistant_turn_text_fn(turn)
        if user_text:
            history.append({"role": "user", "content": user_text})
        if assistant_text:
            history.append({"role": "assistant", "content": assistant_text})
    return history


def planner_history_from_turns(
    turns: list[Any],
    *,
    fallback_history: list[dict[str, str]] | None,
    planner_history_limit: int,
    history_from_turns_fn,
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for item in list(fallback_history or []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant", "system", "developer"} and content:
            merged.append({"role": role, "content": content})
    merged.extend(history_from_turns_fn(turns))
    return merged[-planner_history_limit:]


def planner_input_items_from_history(
    history: list[dict[str, str]],
    *,
    planner_history_limit: int,
    history_item_from_rollout_payload_fn,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in list(history or []):
        normalized = history_item_from_rollout_payload_fn(item)
        if normalized is None:
            continue
        items.append(
            {
                "type": "message",
                "role": normalized["role"],
                "content": [{"type": "input_text", "text": normalized["content"]}],
            }
        )
    return items[-planner_history_limit:]


def planner_turn_context_replay_items(
    turn_context: Any | None,
    *,
    planner_developer_input_item_fn,
    render_workspace_reference_context_item_message_fn,
) -> list[dict[str, Any]]:
    if turn_context is None:
        return []
    items: list[dict[str, Any]] = [
        planner_developer_input_item_fn(
            sandbox_mode=str(turn_context.sandbox_mode or "workspace-write"),
            approval_policy=str(turn_context.approval_policy or "on-request"),
            network_access_enabled=bool(turn_context.network_access_enabled),
        )
    ]
    for input_item in list(turn_context.items or []):
        items.append(input_item.item.to_dict())
    for context_item in list(turn_context.reference_context_items or []):
        rendered = render_workspace_reference_context_item_message_fn(context_item.to_dict())
        if not rendered:
            continue
        items.append(
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": rendered}],
            }
        )
    return items


def turn_used_provider(turn: Any, *, turn_has_structured_tool_items_fn) -> bool:
    protocol_diagnostics = dict(getattr(turn, "protocol_diagnostics", {}) or {})
    protocol_path = dict(protocol_diagnostics.get("protocol_path") or {})
    if bool(protocol_path.get("provider_used", True)):
        return True
    return bool(list(turn.tool_events or [])) or turn_has_structured_tool_items_fn(turn)


def planner_items_from_turn(
    turn: Any,
    *,
    preferred_assistant_turn_text_fn,
    turn_has_tool_history_fn,
    assistant_text_from_turn_events_fn,
    response_items_with_canonical_final_message_fn,
    response_items_with_tool_outputs_fn,
    replay_input_items_from_turn_events_fn,
) -> list[dict[str, Any]]:
    user_text = str(turn.user_text or "").strip()
    items: list[dict[str, Any]] = []
    if user_text:
        items.append(
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": user_text}],
            }
        )
    has_tool_history = turn_has_tool_history_fn(turn)
    if turn.response_items:
        response_items = [item.to_dict() for item in list(turn.response_items or [])]
        if has_tool_history:
            turn_events = [dict(item) for item in list(turn.turn_events or []) if isinstance(item, dict)]
            if assistant_text_from_turn_events_fn(turn_events):
                response_items = response_items_with_canonical_final_message_fn(response_items, turn_events)
            response_items = response_items_with_tool_outputs_fn(
                response_items,
                turn_events,
                [item.to_dict() for item in list(turn.tool_events or [])],
            )
        items.extend(response_items)
        return items
    turn_events = [dict(item) for item in list(turn.turn_events or []) if isinstance(item, dict)]
    if turn_events:
        replay_items = replay_input_items_from_turn_events_fn(turn_events)
        if replay_items:
            items.extend(replay_items)
            return items
    if has_tool_history:
        items.extend(
            response_items_with_tool_outputs_fn(
                [],
                turn_events,
                [item.to_dict() for item in list(turn.tool_events or [])],
            )
        )
        return items
    assistant_text = preferred_assistant_turn_text_fn(turn, include_response_items=False)
    if assistant_text:
        items.append(
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "input_text", "text": assistant_text}],
            }
        )
    return items


def response_item_seed_from_history(
    item: dict[str, Any],
    *,
    response_input_item_from_dict_fn: Callable[[dict[str, Any]], Any],
    response_input_item_type: type,
    history_item_from_rollout_payload_fn,
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    source = item.get("item")
    if isinstance(source, dict):
        item = dict(source)
    if str(item.get("type") or item.get("item_type") or "").strip():
        return response_input_item_from_dict_fn(item).to_dict()
    normalized = history_item_from_rollout_payload_fn(item)
    if normalized is None:
        return None
    content_type = "output_text" if normalized["role"] == "assistant" else "input_text"
    return response_input_item_type(
        item_type="message",
        role=normalized["role"],
        content=[{"type": content_type, "text": normalized["content"]}],
    ).to_dict()


def rollout_seed_items_from_history(
    history: list[dict[str, Any]],
    *,
    now_iso_fn: Callable[[], str],
    response_item_seed_from_history_fn,
) -> list[dict[str, Any]]:
    timestamp = now_iso_fn()
    items: list[dict[str, Any]] = []
    for entry in list(history or []):
        normalized = response_item_seed_from_history_fn(entry)
        if normalized is None:
            continue
        items.append({"type": "response_item", "timestamp": timestamp, "item": normalized})
    return items
