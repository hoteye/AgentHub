from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.models import ResponseInputItem, response_items_to_text
from cli.agent_cli.models_response_projection import shared_replay_reasoning_retention_diagnostics


_SHARED_REPLAY_REASONING_DIAGNOSTICS_ATTR = "_shared_replay_reasoning_retention_diagnostics"


def _record_shared_replay_reasoning_diagnostics(runtime: Any, turn: Dict[str, Any]) -> None:
    diagnostics = shared_replay_reasoning_retention_diagnostics(turn)
    if not diagnostics:
        return
    existing = list(getattr(runtime, _SHARED_REPLAY_REASONING_DIAGNOSTICS_ATTR, []) or [])
    existing.extend(dict(item) for item in diagnostics if isinstance(item, dict))
    setattr(runtime, _SHARED_REPLAY_REASONING_DIAGNOSTICS_ATTR, existing)


def projected_assistant_turn_text(runtime: Any, turn: Dict[str, Any]) -> str:
    turn_events = [dict(item) for item in list(turn.get("turn_events") or []) if isinstance(item, dict)]
    response_item_text = response_items_to_text(
        [
            ResponseInputItem.from_dict(item)
            for item in list(turn.get("response_items") or [])
            if isinstance(item, dict)
        ]
    ).strip()
    return runtime._preferred_assistant_turn_text(
        turn_events=turn_events,
        assistant_history_text=str(turn.get("assistant_history_text") or "").strip(),
        response_item_text=response_item_text,
        assistant_fallback_text=str(turn.get("assistant_text") or "").strip(),
    )


def projected_history_from_turn(runtime: Any, turn: Dict[str, Any]) -> List[Dict[str, str]]:
    if not isinstance(turn, dict):
        return []
    if not runtime._turn_used_provider(turn):
        return []
    _record_shared_replay_reasoning_diagnostics(runtime, turn)
    projected: List[Dict[str, str]] = []
    user_text = str(turn.get("user_text") or "").strip()
    assistant_text = projected_assistant_turn_text(runtime, turn)
    if user_text:
        projected.append({"role": "user", "content": user_text})
    if assistant_text:
        projected.append({"role": "assistant", "content": assistant_text})
    return projected


def projected_history_from_turns(runtime: Any, turns: Any) -> List[Dict[str, str]]:
    projected: List[Dict[str, str]] = []
    for turn in list(turns or []):
        projected.extend(projected_history_from_turn(runtime, turn))
    return projected


def merged_planner_history(
    runtime: Any,
    *,
    base_history: Any,
    history_turns: Any,
    fallback_history: Any,
) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    for item in list(base_history or []):
        normalized = runtime._normalized_history_item(item)
        if normalized is not None:
            merged.append(normalized)
    merged.extend(projected_history_from_turns(runtime, history_turns))
    if merged:
        return merged[-runtime._PLANNER_HISTORY_LIMIT_MESSAGES :]

    fallback: List[Dict[str, str]] = []
    for item in list(fallback_history or []):
        normalized = runtime._normalized_history_item(item)
        if normalized is not None:
            fallback.append(normalized)
    return fallback[-runtime._PLANNER_HISTORY_LIMIT_MESSAGES :]


def planner_history(runtime: Any) -> List[Dict[str, str]]:
    setattr(runtime, _SHARED_REPLAY_REASONING_DIAGNOSTICS_ATTR, [])
    return merged_planner_history(
        runtime,
        base_history=runtime._base_history,
        history_turns=runtime.history_turns,
        fallback_history=runtime.history,
    )
