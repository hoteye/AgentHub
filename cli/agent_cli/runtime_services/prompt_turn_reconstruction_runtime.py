from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.models import RolloutItem
from cli.agent_cli.thread_store import ThreadStore


def append_rollout_item(runtime: Any, payload: Dict[str, Any]) -> None:
    item = dict(payload or {})
    runtime.rollout_items.append(item)
    if len(runtime.rollout_items) > 200:
        runtime.rollout_items = runtime.rollout_items[-200:]
    item_type = str(item.get("type") or "").strip()
    if item_type == "turn_context" and str(item.get("scope") or "").strip() == "turn_context":
        _apply_turn_context_rollout_item(runtime, item)
        return
    if item_type == "response_item" and str(item.get("scope") or "").strip() == "turn_context":
        _apply_scoped_response_item(runtime, item)
        return
    if item_type == "reference_context_item" and str(item.get("scope") or "").strip() == "turn_context":
        _apply_scoped_reference_context_item(runtime, item)
        return
    if item_type == "state_snapshot" and str(item.get("scope") or "").strip() == "turn_context":
        _apply_scoped_state_snapshot(runtime, item)
        return
    if item_type == "compacted":
        replacement_history = ThreadStore._compacted_replacement_history(
            item,
            existing_history=runtime._planner_history(),
        )
        runtime._apply_compaction_state(replacement_history)
        return
    turn = _turn_payload_from_rollout_item(item)
    if turn is None:
        return
    runtime._append_history_turn(turn)


def _apply_turn_context_rollout_item(runtime: Any, item: Dict[str, Any]) -> None:
    rollout_item = RolloutItem.from_dict(item)
    turn_context = rollout_item.turn_context
    if turn_context is None:
        return
    for raw_input_item in list(turn_context.items or []):
        source_name = "environment" if raw_input_item.source == "environment_context" else "workspace"
        normalized_item = runtime._normalized_planner_input_item(raw_input_item.item.to_dict())
        if normalized_item is None:
            continue
        text = "\n".join(
            str(block.get("text") or "").strip()
            for block in list(normalized_item.get("content") or [])
            if isinstance(block, dict) and str(block.get("text") or "").strip()
        )
        normalized_history_item = runtime._normalized_history_item(
            {
                "role": normalized_item.get("role"),
                "content": text,
            }
        )
        if normalized_history_item is not None:
            runtime._append_context_history_item(source_name, normalized_history_item)
    for scoped_item in list(turn_context.reference_context_items or []):
        runtime._append_reference_context_item(scoped_item.to_dict())
    _apply_turn_context_state(runtime, turn_context.state)


def _apply_scoped_response_item(runtime: Any, item: Dict[str, Any]) -> None:
    scoped_item = item.get("item")
    if isinstance(scoped_item, dict):
        source_name = str(item.get("source") or "").strip()
        runtime._append_context_history_item(
            "environment" if source_name == "environment_context" else "workspace",
            scoped_item,
        )


def _apply_scoped_reference_context_item(runtime: Any, item: Dict[str, Any]) -> None:
    scoped_item = item.get("item")
    if isinstance(scoped_item, dict):
        runtime._append_reference_context_item(scoped_item)


def _apply_scoped_state_snapshot(runtime: Any, item: Dict[str, Any]) -> None:
    state = item.get("state")
    if isinstance(state, dict):
        _apply_turn_context_state(runtime, state)


def _apply_turn_context_state(runtime: Any, state: Dict[str, Any]) -> None:
    if not isinstance(state, dict):
        return
    environment_snapshot = state.get("environment_context_snapshot")
    workspace_snapshot = state.get("workspace_context_snapshot")
    memory_snapshot = state.get("memory_context_snapshot")
    if isinstance(environment_snapshot, dict):
        runtime._environment_context_snapshot = dict(environment_snapshot)
    if isinstance(workspace_snapshot, dict):
        runtime._workspace_context_snapshot = dict(workspace_snapshot)
    if isinstance(memory_snapshot, dict):
        runtime._memory_context_snapshot = dict(memory_snapshot)


def _turn_payload_from_rollout_item(item: Dict[str, Any]) -> Dict[str, Any] | None:
    turn = item.get("turn")
    if not isinstance(turn, dict):
        return None
    if "reference_context_items" in turn or not isinstance(item.get("reference_context_items"), list):
        return dict(turn)
    return {
        **dict(turn),
        "reference_context_items": list(item.get("reference_context_items") or []),
    }
