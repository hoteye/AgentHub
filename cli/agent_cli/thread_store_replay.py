from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli import thread_store_replay_mapping_runtime as replay_mapping_runtime
from cli.agent_cli import (
    thread_store_replay_projection_helpers_runtime as replay_projection_helpers_service,
)
from cli.agent_cli import thread_store_replay_pure_helpers_runtime as replay_pure_helpers_service
from cli.agent_cli import thread_store_replay_runtime as replay_runtime
from cli.agent_cli.models import (
    ReferenceContextItem,
    ResponseInputItem,
    ThreadHistoryTurn,
    TurnContextRollout,
    response_items_to_text,
    replay_input_items_from_turn_events,
    response_items_with_tool_outputs,
)
from cli.agent_cli.runtime_policy import render_permissions_instructions
from cli.agent_cli.workspace_context import render_workspace_reference_context_item_message

PLANNER_HISTORY_LIMIT_MESSAGES = 24


def history_item_from_rollout_payload(payload: Dict[str, Any]) -> Dict[str, str] | None:
    return replay_mapping_runtime.history_item_from_rollout_payload(payload)


def response_input_item_from_rollout_payload(payload: Dict[str, Any]) -> Dict[str, Any] | None:
    return replay_mapping_runtime.response_input_item_from_rollout_payload(
        payload,
        response_input_item_from_dict_fn=ResponseInputItem.from_dict,
    )


def history_item_from_planner_input_item(payload: Dict[str, Any]) -> Dict[str, str] | None:
    return replay_mapping_runtime.history_item_from_planner_input_item(
        payload,
        history_item_from_rollout_payload_fn=history_item_from_rollout_payload,
    )


def reference_context_item_from_rollout_payload(payload: Dict[str, Any]) -> ReferenceContextItem | None:
    return replay_mapping_runtime.reference_context_item_from_rollout_payload(
        payload,
        reference_context_item_from_dict_fn=ReferenceContextItem.from_dict,
    )


def state_snapshot_from_rollout_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return replay_mapping_runtime.state_snapshot_from_rollout_payload(payload)


def rollback_turn_count(payload: Dict[str, Any]) -> int:
    return replay_mapping_runtime.rollback_turn_count(payload)


def compacted_replacement_history(
    payload: Dict[str, Any],
    *,
    existing_history: List[Dict[str, str]] | None = None,
) -> List[Dict[str, str]]:
    return replay_mapping_runtime.compacted_replacement_history(
        payload,
        existing_history=existing_history,
        history_item_from_rollout_payload_fn=history_item_from_rollout_payload,
    )


def tool_item_events_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return replay_runtime.tool_item_events_from_turn_events(turn_events)


def turn_has_structured_tool_items(turn: ThreadHistoryTurn) -> bool:
    return replay_runtime.turn_has_structured_tool_items(turn)


def turn_has_tool_history(turn: ThreadHistoryTurn) -> bool:
    return replay_runtime.turn_has_tool_history(turn)


def assistant_text_from_turn_events(turn_events: List[Dict[str, Any]]) -> str:
    return replay_runtime.assistant_text_from_turn_events(turn_events)


def response_items_with_canonical_final_message(
    response_items: List[Dict[str, Any]],
    turn_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return replay_runtime.response_items_with_canonical_final_message(
        response_items,
        turn_events,
    )


def preferred_assistant_turn_text(
    turn: ThreadHistoryTurn,
    *,
    include_response_items: bool = True,
) -> str:
    return replay_runtime.preferred_assistant_turn_text(
        turn,
        response_items_to_text_fn=response_items_to_text,
        include_response_items=include_response_items,
    )


def history_from_turns(turns: List[ThreadHistoryTurn]) -> List[Dict[str, str]]:
    return replay_mapping_runtime.history_from_turns(
        turns,
        preferred_assistant_turn_text_fn=preferred_assistant_turn_text,
    )


def planner_history_from_turns(
    turns: List[ThreadHistoryTurn],
    *,
    fallback_history: List[Dict[str, str]] | None = None,
    planner_history_limit: int = PLANNER_HISTORY_LIMIT_MESSAGES,
) -> List[Dict[str, str]]:
    return replay_mapping_runtime.planner_history_from_turns(
        turns,
        fallback_history=fallback_history,
        planner_history_limit=planner_history_limit,
        history_from_turns_fn=history_from_turns,
    )


def planner_input_items_from_history(
    history: List[Dict[str, str]],
    *,
    planner_history_limit: int = PLANNER_HISTORY_LIMIT_MESSAGES,
) -> List[Dict[str, Any]]:
    return replay_mapping_runtime.planner_input_items_from_history(
        history,
        planner_history_limit=planner_history_limit,
        history_item_from_rollout_payload_fn=history_item_from_rollout_payload,
    )


def planner_developer_input_item(
    *,
    sandbox_mode: str,
    approval_policy: str,
    network_access_enabled: bool,
) -> Dict[str, Any]:
    return {
        "type": "message",
        "role": "developer",
        "content": [
            {
                "type": "input_text",
                "text": render_permissions_instructions(
                    sandbox_mode=sandbox_mode,
                    approval_policy=approval_policy,
                    network_access_enabled=network_access_enabled,
                ),
            }
        ],
    }


def planner_turn_context_replay_items(turn_context: TurnContextRollout | None) -> List[Dict[str, Any]]:
    return replay_mapping_runtime.planner_turn_context_replay_items(
        turn_context,
        planner_developer_input_item_fn=planner_developer_input_item,
        render_workspace_reference_context_item_message_fn=render_workspace_reference_context_item_message,
    )


def media_artifact_handle(payload: dict[str, Any]) -> str:
    return replay_pure_helpers_service.media_artifact_handle(payload)


def media_artifact_persistence_state_from_turn(turn: ThreadHistoryTurn) -> dict[str, Any]:
    return replay_projection_helpers_service.media_artifact_persistence_state_from_turn(turn)


def merge_media_artifact_persistence_state(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    return replay_projection_helpers_service.merge_media_artifact_persistence_state(
        existing,
        incoming,
    )


def planner_turn_response_replay_items(turn: ThreadHistoryTurn) -> List[Dict[str, Any]]:
    return replay_projection_helpers_service.planner_turn_response_replay_items(turn)


def turn_used_provider(turn: ThreadHistoryTurn) -> bool:
    return replay_mapping_runtime.turn_used_provider(
        turn,
        turn_has_structured_tool_items_fn=turn_has_structured_tool_items,
    )


def planner_input_items_from_turns(
    turns: List[ThreadHistoryTurn],
    *,
    fallback_history: List[Dict[str, str]] | None = None,
    planner_history_limit: int = PLANNER_HISTORY_LIMIT_MESSAGES,
    turn_used_provider_fn: Callable[[ThreadHistoryTurn], bool] | None = None,
) -> List[Dict[str, Any]]:
    uses_provider = turn_used_provider_fn or turn_used_provider
    return replay_projection_helpers_service.planner_input_items_from_turns(
        turns,
        fallback_history=fallback_history,
        planner_history_limit=planner_history_limit,
        planner_input_items_from_history_fn=planner_input_items_from_history,
        turn_used_provider_fn=uses_provider,
    )


def planner_input_items_from_rollout_items(
    rollout_items: List[Dict[str, Any]],
    *,
    fallback_history: List[Dict[str, str]] | None = None,
    planner_history_limit: int = PLANNER_HISTORY_LIMIT_MESSAGES,
    turn_used_provider_fn: Callable[[ThreadHistoryTurn], bool] | None = None,
) -> List[Dict[str, Any]]:
    uses_provider = turn_used_provider_fn or turn_used_provider
    return replay_projection_helpers_service.planner_input_items_from_rollout_items(
        rollout_items,
        fallback_history=fallback_history,
        planner_history_limit=planner_history_limit,
        turn_used_provider_fn=uses_provider,
        compacted_replacement_history_fn=compacted_replacement_history,
        planner_input_items_from_history_fn=planner_input_items_from_history,
        planner_turn_context_replay_items_fn=planner_turn_context_replay_items,
        planner_input_items_from_turns_fn=planner_input_items_from_turns,
    )


def name_from_history(
    history: List[Dict[str, Any]],
    *,
    derive_name: Callable[[str], str],
) -> str:
    for item in list(history or []):
        if not isinstance(item, dict):
            continue
        normalized = history_item_from_rollout_payload(item)
        if normalized is None or normalized["role"] != "user":
            continue
        return derive_name(normalized["content"])
    return ""


def response_item_seed_from_history(item: Dict[str, Any]) -> Dict[str, Any] | None:
    return replay_mapping_runtime.response_item_seed_from_history(
        item,
        response_input_item_from_dict_fn=ResponseInputItem.from_dict,
        response_input_item_type=ResponseInputItem,
        history_item_from_rollout_payload_fn=history_item_from_rollout_payload,
    )


def rollout_seed_items_from_history(
    history: List[Dict[str, Any]],
    *,
    now_iso_fn: Callable[[], str],
) -> List[Dict[str, Any]]:
    return replay_mapping_runtime.rollout_seed_items_from_history(
        history,
        now_iso_fn=now_iso_fn,
        response_item_seed_from_history_fn=response_item_seed_from_history,
    )
