from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.environment_context import (
    environment_contract,
)
from cli.agent_cli.models import (
    ReferenceContextItem,
    ResponseInputItem,
    RolloutItem,
    TurnContextRollout,
    replay_input_items_from_turn_events,
    response_items_to_text,
    response_items_with_tool_outputs,
)
from cli.agent_cli.provider import (
    build_ordered_request_prelude_items,
    request_prelude_contract,
)
from cli.agent_cli.runtime_policy import render_permissions_instructions
from cli.agent_cli.runtime_services import (
    planner_context_derivation_runtime as context_derivation_runtime,
    planner_context_history_runtime as history_runtime,
    planner_context_runtime_helpers as planner_context_runtime_helpers,
)
from cli.agent_cli import thread_store_replay_mapping_runtime as replay_mapping_runtime
from cli.agent_cli.thread_store import ThreadStore
from cli.agent_cli.workspace_context import (
    render_workspace_reference_context_item_message,
    workspace_contract,
)

planner_message_input_item = history_runtime.planner_message_input_item
planner_message_history_input_items = history_runtime.planner_message_history_input_items


def workspace_snapshot_has_context(snapshot: Optional[Dict[str, Any]]) -> bool:
    return context_derivation_runtime.workspace_snapshot_has_context(snapshot)


def _is_workspace_context_payload(payload: Dict[str, Any]) -> bool:
    return planner_context_runtime_helpers.is_workspace_context_payload(payload)


def planner_context_input_items(
    runtime: Any,
    *,
    environment_snapshot: Dict[str, Any],
    workspace_snapshot: Dict[str, Any],
    pending_environment_messages: Optional[List[Dict[str, str]]] = None,
    pending_context_messages: Optional[List[Dict[str, str]]] = None,
    pending_context_items: Optional[List[ReferenceContextItem]] = None,
    environment_baseline_missing: bool = False,
    workspace_baseline_missing: bool = False,
    prefer_restored_environment_history: bool = False,
    prefer_restored_workspace_history: bool = False,
) -> List[Dict[str, Any]]:
    return planner_context_runtime_helpers.planner_context_input_items(
        runtime,
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        pending_environment_messages=pending_environment_messages,
        pending_context_messages=pending_context_messages,
        pending_context_items=pending_context_items,
        environment_baseline_missing=environment_baseline_missing,
        workspace_baseline_missing=workspace_baseline_missing,
        prefer_restored_environment_history=prefer_restored_environment_history,
        prefer_restored_workspace_history=prefer_restored_workspace_history,
        planner_developer_input_item_fn=planner_developer_input_item,
        planner_message_history_input_items_fn=planner_message_history_input_items,
        workspace_snapshot_has_context_fn=workspace_snapshot_has_context,
        build_ordered_request_prelude_items_fn=build_ordered_request_prelude_items,
    )


def request_contract_payload(
    *,
    environment_snapshot: Dict[str, Any],
    workspace_snapshot: Dict[str, Any],
    prelude_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "request_contract": {
            "environment": environment_contract(environment_snapshot),
            "workspace": workspace_contract(workspace_snapshot),
            "prelude": request_prelude_contract(prelude_items),
        }
    }


def planner_base_history_input_items(runtime: Any) -> List[Dict[str, Any]]:
    return planner_message_history_input_items(runtime, runtime._base_history)


def planner_developer_input_item(
    *,
    sandbox_mode: str,
    approval_policy: str,
    network_access_enabled: bool,
    writable_roots: Optional[List[str]] = None,
    skills_instructions: str = "",
) -> Dict[str, Any]:
    content = [
        {
            "type": "input_text",
            "text": render_permissions_instructions(
                sandbox_mode=sandbox_mode,
                approval_policy=approval_policy,
                network_access_enabled=network_access_enabled,
                writable_roots=writable_roots,
            ),
        }
    ]
    normalized_skills = str(skills_instructions or "").strip()
    if normalized_skills:
        content.append({"type": "input_text", "text": normalized_skills})
    return {
        "type": "message",
        "role": "developer",
        "content": content,
    }


def planner_turn_context_replay_items(
    runtime: Any,
    turn_context: TurnContextRollout | None,
) -> List[Dict[str, Any]]:
    if turn_context is None:
        return []
    effective_policy = planner_context_runtime_helpers.effective_prompt_runtime_policy(
        runtime,
        approval_policy=str(turn_context.approval_policy or runtime.runtime_policy.approval_policy),
        sandbox_mode=str(turn_context.sandbox_mode or runtime.runtime_policy.sandbox_mode),
    )
    developer_item = planner_developer_input_item(
        sandbox_mode=str(effective_policy.get("sandbox_mode") or ""),
        approval_policy=str(effective_policy.get("approval_policy") or ""),
        network_access_enabled=bool(
            runtime.web_access_allowed()
            if turn_context.network_access_enabled is None
            else turn_context.network_access_enabled
        ),
    )
    environment_items: List[Dict[str, Any]] = []
    workspace_message_items: List[Dict[str, Any]] = []
    for input_item in list(turn_context.items or []):
        normalized = runtime._normalized_planner_input_item(input_item.item.to_dict())
        if normalized is not None:
            if input_item.source == "environment_context":
                environment_items.append(normalized)
            else:
                workspace_message_items.append(normalized)
    for context_item in list(turn_context.reference_context_items or []):
        rendered = render_workspace_reference_context_item_message(context_item.to_dict())
        message_item = planner_message_input_item("user", rendered or "")
        if message_item is not None:
            workspace_message_items.append(message_item)
    return build_ordered_request_prelude_items(
        developer_item=developer_item,
        environment_items=environment_items,
        workspace_reference_items=[],
        workspace_message_items=workspace_message_items,
    )


def planner_turn_response_replay_items(runtime: Any, turn: Dict[str, Any]) -> List[Dict[str, Any]]:
    return planner_context_runtime_helpers.planner_turn_response_replay_items(
        runtime,
        turn,
        planner_message_input_item_fn=planner_message_input_item,
    )


def planner_conversation_rollout_items(runtime: Any) -> List[Dict[str, Any]]:
    if not runtime.rollout_items:
        return []
    item_segments: List[List[Dict[str, Any]]] = []
    pending_turn_context: TurnContextRollout | None = None
    saw_turn = False
    for raw_item in list(runtime.rollout_items or []):
        if not isinstance(raw_item, dict):
            continue
        rollout_item = RolloutItem.from_dict(raw_item)
        if rollout_item.item_type == "compacted":
            replacement_history = ThreadStore._compacted_replacement_history(
                rollout_item.payload,
                existing_history=runtime._planner_history(),
            )
            item_segments = [
                [item] for item in planner_message_history_input_items(runtime, replacement_history)
            ]
            pending_turn_context = None
            saw_turn = False
            continue
        if rollout_item.item_type == "turn_context":
            pending_turn_context = rollout_item.turn_context
            continue
        if rollout_item.item_type != "turn" or rollout_item.turn is None:
            continue
        saw_turn = True
        turn_payload = rollout_item.turn.to_dict()
        if not runtime._turn_used_provider(turn_payload):
            pending_turn_context = None
            continue
        turn_segment: List[Dict[str, Any]] = []
        turn_segment.extend(planner_turn_context_replay_items(runtime, pending_turn_context))
        pending_turn_context = None
        user_text = str(turn_payload.get("user_text") or "").strip()
        if user_text:
            message_item = planner_message_input_item("user", user_text)
            if message_item is not None:
                turn_segment.append(message_item)
        turn_segment.extend(planner_turn_response_replay_items(runtime, turn_payload))
        item_segments.append(turn_segment)
    if saw_turn and item_segments:
        return replay_mapping_runtime.bounded_turn_segment_tail(
            item_segments,
            planner_history_limit=runtime._PLANNER_HISTORY_LIMIT_MESSAGES,
        )
    return []


def planner_conversation_turn_items(runtime: Any) -> List[Dict[str, Any]]:
    rollout_items = planner_conversation_rollout_items(runtime)
    if rollout_items:
        return rollout_items
    turn_segments: List[List[Dict[str, Any]]] = [
        [item] for item in planner_base_history_input_items(runtime)
    ]
    for turn in list(runtime.history_turns or []):
        if not isinstance(turn, dict):
            continue
        if not runtime._turn_used_provider(turn):
            continue
        turn_segment: List[Dict[str, Any]] = []
        user_text = str(turn.get("user_text") or "").strip()
        if user_text:
            message_item = planner_message_input_item("user", user_text)
            if message_item is not None:
                turn_segment.append(message_item)
        response_items = [
            dict(item)
            for item in list(turn.get("response_items") or [])
            if isinstance(item, dict)
        ]
        turn_events = [dict(item) for item in list(turn.get("turn_events") or []) if isinstance(item, dict)]
        tool_events = [dict(item) for item in list(turn.get("tool_events") or []) if isinstance(item, dict)]
        assistant_history_text = str(turn.get("assistant_history_text") or "").strip()
        assistant_fallback_text = str(turn.get("assistant_text") or "").strip()
        response_item_text = response_items_to_text(
            [
                ResponseInputItem.from_dict(item)
                for item in list(response_items or [])
                if isinstance(item, dict)
            ]
        ).strip()
        preferred_assistant_text = runtime._preferred_assistant_turn_text(
            turn_events=turn_events,
            assistant_history_text=assistant_history_text,
            response_item_text=response_item_text,
            assistant_fallback_text=assistant_fallback_text,
        )
        has_tool_history = bool(tool_events or runtime._turn_events_have_structured_tool_items(turn_events))
        if response_items:
            if has_tool_history:
                if runtime._assistant_text_from_turn_events(turn_events):
                    response_items = runtime._response_items_with_canonical_final_message(response_items, turn_events)
                response_items = response_items_with_tool_outputs(response_items, turn_events, tool_events)
            turn_segment.extend(response_items)
            turn_segments.append(turn_segment)
            continue
        if turn_events:
            replay_items = replay_input_items_from_turn_events(turn_events)
            if replay_items:
                turn_segment.extend(replay_items)
                turn_segments.append(turn_segment)
                continue
        if has_tool_history:
            turn_segment.extend(response_items_with_tool_outputs([], turn_events, tool_events))
            turn_segments.append(turn_segment)
            continue
        message_item = planner_message_input_item("assistant", preferred_assistant_text)
        if message_item is not None:
            turn_segment.append(message_item)
        turn_segments.append(turn_segment)
    return replay_mapping_runtime.bounded_turn_segment_tail(
        turn_segments,
        planner_history_limit=runtime._PLANNER_HISTORY_LIMIT_MESSAGES,
    )


def planner_conversation_item_count(runtime: Any) -> int:
    return len(planner_conversation_turn_items(runtime))


def history_summary_text_for_turn(runtime: Any, turn: Dict[str, Any]) -> str:
    return history_runtime.history_summary_text_for_turn(turn)


def build_auto_compaction_replacement_history(
    runtime: Any,
    *,
    instructions: str = "",
    prefer_model_summary: bool = False,
) -> List[Dict[str, str]]:
    from cli.agent_cli.runtime_services import context_compaction_runtime

    return context_compaction_runtime.build_compaction_replacement_history(
        runtime,
        instructions=instructions,
        prefer_model_summary=prefer_model_summary,
    )


def planner_environment_context_items(
    runtime: Any,
    *,
    snapshot_override: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    return context_derivation_runtime.planner_environment_context_items(
        runtime,
        snapshot_override=snapshot_override,
    )


def planner_workspace_context_items(
    runtime: Any,
    *,
    snapshot_override: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    return context_derivation_runtime.planner_workspace_context_items(
        runtime,
        snapshot_override=snapshot_override,
    )


def planner_history_with_context_updates(
    runtime: Any,
    *,
    planner_history: Optional[List[Dict[str, str]]] = None,
    environment_snapshot: Optional[Dict[str, Any]] = None,
    workspace_snapshot: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    return context_derivation_runtime.planner_history_with_context_updates(
        runtime,
        planner_history=planner_history,
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
    )
