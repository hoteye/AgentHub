from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.models import ResponseInputItem, response_items_to_text
from cli.agent_cli.models_response_projection import shared_replay_reasoning_projection


_SHARED_REPLAY_REASONING_DIAGNOSTICS_ATTR = "_shared_replay_reasoning_retention_diagnostics"


def _record_shared_replay_reasoning_diagnostic(runtime: Any, diagnostic: Dict[str, Any] | None) -> None:
    if not isinstance(diagnostic, dict) or not diagnostic:
        return
    existing = list(getattr(runtime, _SHARED_REPLAY_REASONING_DIAGNOSTICS_ATTR, []) or [])
    existing.append(dict(diagnostic))
    setattr(runtime, _SHARED_REPLAY_REASONING_DIAGNOSTICS_ATTR, existing)


def planner_message_input_item(role: str, content: str) -> Dict[str, Any] | None:
    normalized_role = str(role or "user").strip().lower() or "user"
    normalized_content = str(content or "").strip()
    if not normalized_content:
        return None
    return {
        "type": "message",
        "role": normalized_role,
        "content": [
            {
                "type": "input_text",
                "text": normalized_content,
            }
        ],
    }


def planner_message_history_input_items(
    runtime: Any,
    history: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in list(history or []):
        normalized_item = None
        normalize_item = getattr(runtime, "_normalized_planner_input_item", None)
        if callable(normalize_item):
            normalized_item = normalize_item(raw)
        if normalized_item is None:
            normalized = runtime._normalized_history_item(raw)
            if normalized is None:
                continue
            normalized_item = planner_message_input_item(
                normalized["role"],
                normalized["content"],
            )
        if not isinstance(normalized_item, dict):
            continue
        item_type = str(normalized_item.get("type") or "").strip().lower()
        if item_type == "reasoning":
            projection = shared_replay_reasoning_projection(
                normalized_item,
                source="planner_context_history",
            )
            projected = projection.get("input_item")
            if isinstance(projected, dict):
                items.append(dict(projected))
            else:
                _record_shared_replay_reasoning_diagnostic(runtime, projection.get("diagnostic"))
            continue
        if item_type == "message":
            items.append(dict(normalized_item))
    return items


def history_summary_text_for_turn(turn: Dict[str, Any]) -> str:
    assistant_history_text = str(turn.get("assistant_history_text") or "").strip()
    if assistant_history_text:
        return assistant_history_text
    assistant_text = str(turn.get("assistant_text") or "").strip()
    if assistant_text:
        return assistant_text
    response_items = [
        ResponseInputItem.from_dict(item)
        for item in list(turn.get("response_items") or [])
        if isinstance(item, dict)
    ]
    return response_items_to_text(response_items).strip()


def build_auto_compaction_replacement_history(
    runtime: Any,
    *,
    instructions: str = "",
    prefer_model_summary: bool = False,
) -> List[Dict[str, str]]:
    del instructions, prefer_model_summary
    lines: List[str] = []
    for index, turn in enumerate(list(runtime.history_turns or []), start=1):
        if not isinstance(turn, dict):
            continue
        if not runtime._turn_used_provider(turn):
            continue
        user_text = str(turn.get("user_text") or "").strip()
        assistant_text = history_summary_text_for_turn(turn)
        if user_text:
            lines.append(f"{index}. user: {user_text}")
        if assistant_text:
            lines.append(f"{index}. assistant: {assistant_text}")
    summary = "\n".join(lines).strip()
    if not summary:
        return []
    return [{"role": "assistant", "content": "Previous conversation summary:\n" + summary}]
