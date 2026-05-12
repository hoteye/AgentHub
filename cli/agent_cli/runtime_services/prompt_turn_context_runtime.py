from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.models import (
    ReferenceContextItem,
    ResponseInputItem,
    RolloutItem,
    TurnContextInputItem,
    TurnContextRollout,
)
from cli.agent_cli.runtime_services import planner_context_runtime_helpers


def append_context_history_item(runtime: Any, target: str, item: Dict[str, str]) -> None:
    normalized = runtime._normalized_history_item(item)
    if normalized is None:
        return
    history = runtime._environment_context_history if target == "environment" else runtime._context_update_history
    if history and history[-1] == normalized:
        return
    history.append(normalized)
    if len(history) > 16:
        del history[:-16]


def append_reference_context_item(runtime: Any, item: Dict[str, Any]) -> None:
    payload = dict(item or {})
    if not payload:
        return
    if payload not in runtime.reference_context_items:
        runtime.reference_context_items.append(payload)
    if len(runtime.reference_context_items) > 400:
        runtime.reference_context_items = runtime.reference_context_items[-400:]


def turn_context_rollout_items(
    runtime: Any,
    *,
    pending_environment_messages: List[Dict[str, str]],
    pending_context_messages: List[Dict[str, str]],
    pending_context_items: List[ReferenceContextItem],
    next_environment_snapshot: Dict[str, Any],
    next_workspace_snapshot: Dict[str, Any],
) -> List[Dict[str, Any]]:
    environment_input_items = runtime._planner_message_history_input_items(
        list(pending_environment_messages or [])
    )
    # Compatibility: rollout payload persists environment context items only.
    workspace_input_items: List[Dict[str, Any]] = []
    reference_context_items = [
        context_item.to_dict()
        for context_item in list(pending_context_items or [])
    ]
    if not environment_input_items and not workspace_input_items and not reference_context_items:
        return []
    provider_status = runtime.agent.provider_status()
    effective_policy = planner_context_runtime_helpers.effective_prompt_runtime_policy(runtime)
    state_payload = {
        "environment_context_snapshot": dict(next_environment_snapshot or {}),
        "workspace_context_snapshot": dict(next_workspace_snapshot or {}),
    }
    memory_snapshot = dict(getattr(runtime, "_memory_context_snapshot", {}) or {})
    if memory_snapshot:
        state_payload["memory_context_snapshot"] = memory_snapshot
    return [
        RolloutItem(
            item_type="turn_context",
            payload={"scope": "turn_context"},
            turn_context=TurnContextRollout(
                cwd=str(runtime.cwd),
                shell=str(next_environment_snapshot.get("shell") or ""),
                current_date=str(next_environment_snapshot.get("current_date") or ""),
                timezone=str(next_environment_snapshot.get("timezone") or ""),
                approval_policy=str(effective_policy.get("approval_policy") or ""),
                sandbox_mode=str(effective_policy.get("sandbox_mode") or ""),
                model=str(provider_status.get("provider_model") or provider_status.get("model_key") or ""),
                network_access_enabled=runtime.runtime_policy.network_access_enabled,
                items=[
                    *[
                        TurnContextInputItem(
                            source="environment_context",
                            item=ResponseInputItem.from_dict(dict(entry)),
                        )
                        for entry in environment_input_items
                    ],
                    *[
                        TurnContextInputItem(
                            source="workspace_context",
                            item=ResponseInputItem.from_dict(dict(entry)),
                        )
                        for entry in workspace_input_items
                    ],
                ],
                reference_context_items=[
                    ReferenceContextItem.from_dict(dict(entry))
                    for entry in reference_context_items
                ],
                state=state_payload,
            ),
        ).to_dict()
    ]


def apply_turn_context_updates(
    runtime: Any,
    *,
    pending_environment_messages: List[Dict[str, str]],
    pending_context_messages: List[Dict[str, str]],
    pending_context_items: List[ReferenceContextItem],
    next_environment_snapshot: Dict[str, Any],
    next_workspace_snapshot: Dict[str, Any],
) -> None:
    for item in list(pending_environment_messages or []):
        append_context_history_item(runtime, "environment", item)
    for item in list(pending_context_messages or []):
        append_context_history_item(runtime, "workspace", item)
    for item in list(pending_context_items or []):
        append_reference_context_item(runtime, item.to_dict())
    runtime._environment_context_snapshot = dict(next_environment_snapshot or {})
    runtime._workspace_context_snapshot = dict(next_workspace_snapshot or {})
