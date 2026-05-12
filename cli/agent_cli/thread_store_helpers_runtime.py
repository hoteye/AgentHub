from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from cli.agent_cli.models import (
    PromptResponse,
    ReferenceContextItem,
    ResponseInputItem,
    ThreadHistoryTurn,
    compose_turn_events_from_response_items,
    default_response_items,
    response_items_to_text,
)
from cli.agent_cli.models_turn_events_runtime import (
    normalized_plan_payload,
    plan_payload_from_todo_list_item,
)


def assistant_history_text(response: PromptResponse) -> str:
    assistant_text = str(response.assistant_text or "").strip()
    response_items = list(
        response.response_items
        or default_response_items(
            commentary_text=str(response.commentary_text or ""),
            assistant_text=str(response.assistant_text or ""),
        )
    )
    summaries: List[str] = []
    for event in response.tool_events:
        summary = str(event.summary or "").strip()
        if not summary:
            continue
        if summary in summaries:
            continue
        if assistant_text and summary in assistant_text:
            continue
        summaries.append(summary)
    combined_text = response_items_to_text(response_items)
    if combined_text and summaries:
        return combined_text + "\n\n" + "\n".join(summaries)
    if combined_text:
        return combined_text
    if summaries:
        return "\n".join(summaries)
    return ""


def row_to_record(row: Any, *, record_cls: type[Any]) -> Any:
    return record_cls(
        thread_id=str(row["thread_id"]),
        name=str(row["name"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        rollout_path=str(row["rollout_path"]),
        cwd=str(row["cwd"]),
        turn_count=int(row["turn_count"]),
        archived=bool(int(row["archived"])),
        last_user_text=str(row["last_user_text"] or ""),
        last_assistant_text=str(row["last_assistant_text"] or ""),
    )


def derive_name(user_text: str) -> str:
    compact = " ".join(str(user_text or "").split()).strip()
    if not compact:
        return "Thread"
    if len(compact) <= 48:
        return compact
    return compact[:45] + "..."


def turn_replay_requires_structured_tool_output(turn: ThreadHistoryTurn) -> bool:
    for event in list(turn.tool_events or []):
        event_name = str(getattr(event, "name", "") or "").strip()
        if event_name == "request_user_input":
            return True
        if getattr(event, "ok", None) is False:
            return True
    return False


def drop_last_n_user_turns(turns: List[ThreadHistoryTurn], num_turns: int) -> List[ThreadHistoryTurn]:
    if num_turns <= 0:
        return list(turns)
    user_positions = [
        index
        for index, turn in enumerate(turns)
        if str(turn.user_text or "").strip()
    ]
    if not user_positions:
        return list(turns)
    if num_turns >= len(user_positions):
        cut_idx = user_positions[0]
    else:
        cut_idx = user_positions[-num_turns]
    return list(turns[:cut_idx])


def canonical_turn_events(
    response: PromptResponse,
    *,
    response_items: List[ResponseInputItem],
) -> List[Dict[str, Any]]:
    explicit = [dict(item) for item in list(response.turn_events or []) if isinstance(item, dict)]
    if explicit:
        return explicit
    assistant_text = str(response.assistant_text or "")
    visible_assistant_text = str(getattr(response, "command_display_text", "") or "").strip() or assistant_text
    return compose_turn_events_from_response_items(
        assistant_text=visible_assistant_text,
        response_items=list(response_items or []),
    )


def context_items_from_turns(
    turns: List[ThreadHistoryTurn],
    *,
    dedupe_reference_context_items_fn: Any,
) -> List[ReferenceContextItem]:
    items: List[ReferenceContextItem] = []
    for turn in turns:
        items.extend(
            ReferenceContextItem.from_dict(item.to_dict())
            for item in list(turn.reference_context_items or [])
        )
    return dedupe_reference_context_items_fn(items)


def _latest_task_plan_from_turn(turn: ThreadHistoryTurn) -> Dict[str, Any]:
    runtime_state = dict(turn.runtime_state or {})
    latest_from_state = normalized_plan_payload(runtime_state.get("latest_task_plan"))
    if latest_from_state:
        return latest_from_state

    status = dict(turn.status or {})
    latest_from_status = normalized_plan_payload(status.get("latest_task_plan"))
    if latest_from_status:
        return latest_from_status

    for raw_event in reversed(list(turn.turn_events or [])):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "todo_list":
            continue
        payload = plan_payload_from_todo_list_item(item)
        if payload:
            return payload

    for event in reversed(list(turn.tool_events or [])):
        if str(getattr(event, "name", "") or "").strip() != "update_plan":
            continue
        payload = normalized_plan_payload(dict(getattr(event, "payload", {}) or {}))
        if payload:
            return payload
    return {}


def state_from_turns(turns: List[ThreadHistoryTurn]) -> Dict[str, Any]:
    state: Dict[str, Any] = {}
    for turn in reversed(turns):
        if turn.runtime_state:
            state = dict(turn.runtime_state)
            break
        if turn.status:
            state = dict(turn.status)
            break
    latest_task_plan = normalized_plan_payload(state.get("latest_task_plan"))
    if not latest_task_plan:
        for turn in reversed(turns):
            latest_task_plan = _latest_task_plan_from_turn(turn)
            if latest_task_plan:
                break
    if latest_task_plan:
        state = dict(state)
        state["latest_task_plan"] = latest_task_plan
    return state


def turn_used_provider(
    turn: ThreadHistoryTurn,
    *,
    turn_has_structured_tool_items_fn: Any,
) -> bool:
    protocol_diagnostics = dict(getattr(turn, "protocol_diagnostics", {}) or {})
    protocol_path = dict(protocol_diagnostics.get("protocol_path") or {})
    if bool(protocol_path.get("provider_used", True)):
        return True
    return bool(list(turn.tool_events or [])) or turn_has_structured_tool_items_fn(turn)


def iso_to_unix_seconds(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())
