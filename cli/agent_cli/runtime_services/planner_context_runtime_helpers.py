from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from cli.agent_cli import (
    runtime_codex_headless_contract_runtime as codex_headless_contract_runtime_service,
)
from cli.agent_cli.models import (
    ResponseInputItem,
    replay_input_items_from_turn_events,
    response_items_with_tool_outputs,
)
from cli.agent_cli.workspace_context import (
    build_workspace_reference_context_item,
    render_skills_section,
)

_CODEX_OPENAI_PROFILE = "codex_openai"


def _skill_objects_from_snapshot(snapshot: dict[str, Any]) -> list[Any]:
    if not isinstance(snapshot, dict):
        return []
    skills: list[Any] = []
    for item in list(snapshot.get("skills") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        path = str(item.get("path") or "").strip()
        if not name or not description or not path:
            continue
        skills.append(SimpleNamespace(name=name, description=description, path=path))
    return skills


def skills_instructions_from_workspace_snapshot(
    runtime: Any, workspace_snapshot: dict[str, Any]
) -> str:
    if (
        codex_headless_contract_runtime_service.runtime_interaction_profile(runtime)
        != _CODEX_OPENAI_PROFILE
    ):
        return ""
    body = render_skills_section(_skill_objects_from_snapshot(workspace_snapshot))
    if not body:
        return ""
    return f"<skills_instructions>\n{body}\n</skills_instructions>"


def is_workspace_context_payload(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    item_type = str(payload.get("item_type") or "").strip().lower()
    return item_type == "workspace_context"


def _prepend_unique_history_items(
    items: list[dict[str, str]],
    restored_items: list[dict[str, str]],
) -> list[dict[str, str]]:
    seen = {
        (
            str(item.get("role") or "").strip().lower(),
            str(item.get("content") or "").strip(),
        )
        for item in list(items or [])
        if isinstance(item, dict)
    }
    prepended: list[dict[str, str]] = []
    for item in list(restored_items or []):
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("role") or "").strip().lower(),
            str(item.get("content") or "").strip(),
        )
        if key in seen or not key[0] or not key[1]:
            continue
        seen.add(key)
        prepended.append(dict(item))
    return [*prepended, *items]


def effective_prompt_runtime_policy(
    runtime: Any,
    *,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
) -> dict[str, Any]:
    runtime_policy = getattr(runtime, "runtime_policy", None)
    effective = codex_headless_contract_runtime_service.effective_model_runtime_policy(
        runtime,
        approval_policy=(
            approval_policy
            if approval_policy is not None
            else getattr(runtime_policy, "approval_policy", None)
        ),
        sandbox_mode=(
            sandbox_mode
            if sandbox_mode is not None
            else getattr(runtime_policy, "sandbox_mode", None)
        ),
    )
    if bool(effective.get("codex_noninteractive_headless")):
        effective = {**effective, "approval_policy": "never"}
    return effective


def planner_context_input_items(
    runtime: Any,
    *,
    environment_snapshot: dict[str, Any],
    workspace_snapshot: dict[str, Any],
    pending_environment_messages: list[dict[str, str]] | None = None,
    pending_context_messages: list[dict[str, str]] | None = None,
    pending_context_items: list[Any] | None = None,
    environment_baseline_missing: bool = False,
    workspace_baseline_missing: bool = False,
    prefer_restored_environment_history: bool = False,
    prefer_restored_workspace_history: bool = False,
    planner_developer_input_item_fn,
    planner_message_history_input_items_fn,
    workspace_snapshot_has_context_fn,
    build_ordered_request_prelude_items_fn,
) -> list[dict[str, Any]]:
    effective_policy = effective_prompt_runtime_policy(runtime)
    developer_item = planner_developer_input_item_fn(
        sandbox_mode=str(effective_policy.get("sandbox_mode") or ""),
        approval_policy=str(effective_policy.get("approval_policy") or ""),
        network_access_enabled=runtime.web_access_allowed(),
        writable_roots=(
            [str(runtime.cwd)]
            if str(effective_policy.get("sandbox_mode") or "") == "workspace-write" and runtime.cwd
            else None
        ),
        skills_instructions=skills_instructions_from_workspace_snapshot(
            runtime, workspace_snapshot
        ),
    )
    environment_messages = list(pending_environment_messages or [])
    if environment_baseline_missing and prefer_restored_environment_history:
        environment_messages = _prepend_unique_history_items(
            environment_messages,
            runtime._planner_environment_context_items(snapshot_override=None),
        )
    if not environment_messages and environment_baseline_missing:
        if environment_snapshot:
            environment_messages = runtime._planner_environment_context_items(
                snapshot_override=environment_snapshot,
            )
        elif prefer_restored_environment_history:
            environment_messages = runtime._planner_environment_context_items(
                snapshot_override=None
            )
    elif (
        prefer_restored_environment_history
        and not environment_messages
        and not environment_snapshot
    ):
        environment_messages = runtime._planner_environment_context_items(snapshot_override=None)
    environment_items = planner_message_history_input_items_fn(runtime, environment_messages)

    reference_context_payloads: list[dict[str, Any]] = []
    for context_item in list(pending_context_items or []):
        reference_context_payloads.append(context_item.to_dict())
    has_workspace_reference_payload = any(
        is_workspace_context_payload(item) for item in reference_context_payloads
    )
    if (
        not has_workspace_reference_payload
        and workspace_baseline_missing
        and workspace_snapshot_has_context_fn(workspace_snapshot)
    ):
        payload = build_workspace_reference_context_item(None, workspace_snapshot)
        if isinstance(payload, dict):
            reference_context_payloads.append(payload)
    workspace_messages = list(pending_context_messages or [])
    if (
        not reference_context_payloads
        and workspace_baseline_missing
        and prefer_restored_workspace_history
        and not workspace_snapshot_has_context_fn(workspace_snapshot)
    ):
        workspace_messages = _prepend_unique_history_items(
            workspace_messages,
            runtime._planner_workspace_context_items(snapshot_override=None),
        )
    workspace_message_items = planner_message_history_input_items_fn(runtime, workspace_messages)
    return build_ordered_request_prelude_items_fn(
        developer_item=developer_item,
        environment_items=environment_items,
        workspace_reference_items=reference_context_payloads,
        workspace_message_items=workspace_message_items,
    )


def planner_turn_response_replay_items(
    runtime: Any, turn: dict[str, Any], *, planner_message_input_item_fn
) -> list[dict[str, Any]]:
    turn_events = [
        dict(item) for item in list(turn.get("turn_events") or []) if isinstance(item, dict)
    ]
    response_items = []
    for raw_item in list(turn.get("response_items") or []):
        if not isinstance(raw_item, dict):
            continue
        normalized = ResponseInputItem.from_dict(raw_item).to_dict()
        item_type = str(normalized.get("type") or "").strip().lower()
        role = str(normalized.get("role") or "").strip().lower()
        phase = str(normalized.get("phase") or "").strip().lower()
        if item_type == "message" and role == "assistant" and phase == "commentary":
            continue
        response_items.append(normalized)
    tool_events = [
        dict(item) for item in list(turn.get("tool_events") or []) if isinstance(item, dict)
    ]
    has_tool_history = bool(
        tool_events or runtime._turn_events_have_structured_tool_items(turn_events)
    )
    if response_items:
        if has_tool_history:
            if runtime._assistant_text_from_turn_events(turn_events):
                response_items = runtime._response_items_with_canonical_final_message(
                    response_items, turn_events
                )
            return response_items_with_tool_outputs(response_items, turn_events, tool_events)
        return response_items
    if turn_events:
        replay_items = replay_input_items_from_turn_events(turn_events)
        if replay_items:
            return replay_items
    if has_tool_history:
        return response_items_with_tool_outputs([], turn_events, tool_events)
    assistant_text = runtime._preferred_assistant_turn_text(
        turn_events=turn_events,
        assistant_history_text=str(turn.get("assistant_history_text") or "").strip(),
        response_item_text="",
        assistant_fallback_text=str(turn.get("assistant_text") or "").strip(),
    )
    message_item = planner_message_input_item_fn("assistant", assistant_text)
    return [message_item] if message_item is not None else []
