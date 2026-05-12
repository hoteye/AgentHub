from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cli.agent_cli.models import PromptResponse, ReferenceContextItem, ThreadHistoryTurn
from cli.agent_cli import thread_store_replay as replay_helpers
from cli.agent_cli import thread_store_serialization as serialization_helpers


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_rollout_line(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def reference_context_items_from_response(
    response: PromptResponse,
    *,
    reference_context_items_from_tool_event_fn,
    dedupe_reference_context_items_fn,
) -> list[ReferenceContextItem]:
    return serialization_helpers.reference_context_items_from_response(
        response,
        reference_context_items_from_tool_event_fn=reference_context_items_from_tool_event_fn,
        dedupe_reference_context_items_fn=dedupe_reference_context_items_fn,
    )


def history_turn_from_response(
    response: PromptResponse,
    *,
    timestamp: str,
    assistant_history_text: str,
    runtime_state: dict[str, Any] | None = None,
    canonical_turn_events_fn,
    reference_context_items_from_tool_event_fn,
    dedupe_reference_context_items_fn,
    attachment_to_dict_fn,
    tool_event_to_dict_fn,
    activity_event_to_dict_fn,
) -> ThreadHistoryTurn:
    turn = serialization_helpers.history_turn_from_response(
        response,
        timestamp=timestamp,
        assistant_history_text=assistant_history_text,
        runtime_state=runtime_state,
        canonical_turn_events_fn=canonical_turn_events_fn,
        reference_context_items_from_tool_event_fn=reference_context_items_from_tool_event_fn,
        dedupe_reference_context_items_fn=dedupe_reference_context_items_fn,
        attachment_to_dict_fn=attachment_to_dict_fn,
        tool_event_to_dict_fn=tool_event_to_dict_fn,
        activity_event_to_dict_fn=activity_event_to_dict_fn,
    )
    media_state = replay_helpers.media_artifact_persistence_state_from_turn(turn)
    if media_state:
        merged_runtime_state = dict(turn.runtime_state or {})
        merged_runtime_state["media_artifacts"] = replay_helpers.merge_media_artifact_persistence_state(
            merged_runtime_state.get("media_artifacts")
            if isinstance(merged_runtime_state.get("media_artifacts"), dict)
            else {},
            media_state,
        )
        turn.runtime_state = merged_runtime_state
    return turn


def planner_history_from_turns(
    turns: list[ThreadHistoryTurn],
    *,
    fallback_history: list[dict[str, str]] | None = None,
    planner_history_limit: int,
) -> list[dict[str, str]]:
    return replay_helpers.planner_history_from_turns(
        turns,
        fallback_history=fallback_history,
        planner_history_limit=planner_history_limit,
    )


def planner_input_items_from_history(
    history: list[dict[str, str]],
    *,
    planner_history_limit: int,
) -> list[dict[str, Any]]:
    return replay_helpers.planner_input_items_from_history(
        history,
        planner_history_limit=planner_history_limit,
    )


def planner_input_items_from_turns(
    turns: list[ThreadHistoryTurn],
    *,
    fallback_history: list[dict[str, str]] | None = None,
    planner_history_limit: int,
    turn_used_provider_fn,
) -> list[dict[str, Any]]:
    return replay_helpers.planner_input_items_from_turns(
        turns,
        fallback_history=fallback_history,
        planner_history_limit=planner_history_limit,
        turn_used_provider_fn=turn_used_provider_fn,
    )


def planner_input_items_from_rollout_items(
    rollout_items: list[dict[str, Any]],
    *,
    fallback_history: list[dict[str, str]] | None = None,
    planner_history_limit: int,
    turn_used_provider_fn,
) -> list[dict[str, Any]]:
    return replay_helpers.planner_input_items_from_rollout_items(
        rollout_items,
        fallback_history=fallback_history,
        planner_history_limit=planner_history_limit,
        turn_used_provider_fn=turn_used_provider_fn,
    )


def response_items_with_canonical_final_message(
    response_items: list[dict[str, Any]],
    turn_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return replay_helpers.response_items_with_canonical_final_message(
        response_items,
        turn_events,
    )
