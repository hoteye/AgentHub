from __future__ import annotations

from datetime import datetime
from typing import Any

from cli.agent_cli import runtime_runtime
from cli.agent_cli.models import ReferenceContextItem, ResponseInputItem, TurnContextRollout
from cli.agent_cli.runtime_services import (
    planner_context_runtime as planner_context_runtime_service,
)
from cli.agent_cli.runtime_services import prompt_turn_runtime as prompt_turn_runtime_service
from cli.agent_cli.runtime_services import (
    runtime_context_runtime as runtime_context_runtime_service,
)


def _environment_context_turn_update(
    self: Any, *, current_dt: datetime | None = None
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    return runtime_context_runtime_service.environment_context_turn_update(
        self, current_dt=current_dt
    )


def _workspace_context_turn_update(
    self: Any,
) -> tuple[list[dict[str, str]], list[ReferenceContextItem], dict[str, Any]]:
    return runtime_context_runtime_service.workspace_context_turn_update(self)


def _planner_message_input_item(role: str, content: str) -> dict[str, Any] | None:
    return planner_context_runtime_service.planner_message_input_item(role, content)


def _workspace_snapshot_has_context(snapshot: dict[str, Any] | None) -> bool:
    return planner_context_runtime_service.workspace_snapshot_has_context(snapshot)


def _planner_message_history_input_items(
    self: Any, history: list[dict[str, str]]
) -> list[dict[str, Any]]:
    return planner_context_runtime_service.planner_message_history_input_items(self, history)


def _planner_context_input_items(
    self: Any,
    *,
    environment_snapshot: dict[str, Any],
    workspace_snapshot: dict[str, Any],
    pending_environment_messages: list[dict[str, str]] | None = None,
    pending_context_messages: list[dict[str, str]] | None = None,
    pending_context_items: list[ReferenceContextItem] | None = None,
    environment_baseline_missing: bool = False,
    workspace_baseline_missing: bool = False,
    prefer_restored_environment_history: bool = False,
    prefer_restored_workspace_history: bool = False,
) -> list[dict[str, Any]]:
    return planner_context_runtime_service.planner_context_input_items(
        self,
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        pending_environment_messages=pending_environment_messages,
        pending_context_messages=pending_context_messages,
        pending_context_items=pending_context_items,
        environment_baseline_missing=environment_baseline_missing,
        workspace_baseline_missing=workspace_baseline_missing,
        prefer_restored_environment_history=prefer_restored_environment_history,
        prefer_restored_workspace_history=prefer_restored_workspace_history,
    )


def _merge_protocol_diagnostics(*payloads: dict[str, Any] | None) -> dict[str, Any]:
    return prompt_turn_runtime_service.merge_protocol_diagnostics(*payloads)


def _request_contract_payload(
    self: Any,
    *,
    environment_snapshot: dict[str, Any],
    workspace_snapshot: dict[str, Any],
    prelude_items: list[dict[str, Any]],
) -> dict[str, Any]:
    return planner_context_runtime_service.request_contract_payload(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        prelude_items=prelude_items,
    )


def _planner_base_history_input_items(self: Any) -> list[dict[str, Any]]:
    return planner_context_runtime_service.planner_base_history_input_items(self)


def _planner_developer_input_item(
    *,
    sandbox_mode: str,
    approval_policy: str,
    network_access_enabled: bool,
    writable_roots: list[str] | None = None,
    skills_instructions: str = "",
) -> dict[str, Any]:
    return planner_context_runtime_service.planner_developer_input_item(
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        network_access_enabled=network_access_enabled,
        writable_roots=writable_roots,
        skills_instructions=skills_instructions,
    )


def _planner_turn_context_replay_items(
    self: Any, turn_context: TurnContextRollout | None
) -> list[dict[str, Any]]:
    return planner_context_runtime_service.planner_turn_context_replay_items(self, turn_context)


def _planner_turn_response_replay_items(self: Any, turn: dict[str, Any]) -> list[dict[str, Any]]:
    return planner_context_runtime_service.planner_turn_response_replay_items(self, turn)


def _planner_conversation_rollout_items(self: Any) -> list[dict[str, Any]]:
    return planner_context_runtime_service.planner_conversation_rollout_items(self)


def _planner_conversation_turn_items(self: Any) -> list[dict[str, Any]]:
    return planner_context_runtime_service.planner_conversation_turn_items(self)


def _planner_conversation_item_count(self: Any) -> int:
    return planner_context_runtime_service.planner_conversation_item_count(self)


def _history_summary_text_for_turn(self: Any, turn: dict[str, Any]) -> str:
    return planner_context_runtime_service.history_summary_text_for_turn(self, turn)


def _build_auto_compaction_replacement_history(
    self: Any,
    *,
    instructions: str = "",
    prefer_model_summary: bool = False,
) -> list[dict[str, str]]:
    return planner_context_runtime_service.build_auto_compaction_replacement_history(
        self,
        instructions=instructions,
        prefer_model_summary=prefer_model_summary,
    )


def _apply_compaction_state(self: Any, replacement_history: list[dict[str, str]]) -> None:
    prompt_turn_runtime_service.apply_compaction_state(self, replacement_history)


def _maybe_auto_compact_history(self: Any) -> None:
    prompt_turn_runtime_service.maybe_auto_compact_history(self)


def _compact_history(
    self: Any,
    *,
    reason: str,
    trigger: str,
    instructions: str = "",
    prefer_model_summary: bool = True,
) -> dict[str, Any]:
    return prompt_turn_runtime_service.compact_history(
        self,
        reason=reason,
        trigger=trigger,
        instructions=instructions,
        prefer_model_summary=prefer_model_summary,
    )


def _planner_history_input_items(self: Any, history: list[dict[str, str]]) -> list[dict[str, Any]]:
    return self._planner_message_history_input_items(history)


def _normalized_planner_input_item(self: Any, item: Any) -> dict[str, Any] | None:
    return runtime_runtime.normalized_planner_input_item(
        item,
        response_input_item_from_dict_fn=ResponseInputItem.from_dict,
        planner_message_input_item_fn=self._planner_message_input_item,
    )


def _assistant_text_from_turn_events(turn_events: Any) -> str:
    return prompt_turn_runtime_service.assistant_text_from_turn_events(turn_events)


def _turn_events_have_structured_tool_items(turn_events: Any) -> bool:
    return prompt_turn_runtime_service.turn_events_have_structured_tool_items(turn_events)


def _turn_replay_requires_structured_tool_output(tool_events: Any) -> bool:
    return prompt_turn_runtime_service.turn_replay_requires_structured_tool_output(tool_events)


def _response_items_with_canonical_final_message(
    cls: Any,
    response_items: list[dict[str, Any]],
    turn_events: Any,
) -> list[dict[str, Any]]:
    return prompt_turn_runtime_service.response_items_with_canonical_final_message(
        response_items,
        turn_events,
    )


def _preferred_assistant_turn_text(
    cls: Any,
    *,
    turn_events: Any,
    assistant_history_text: str,
    response_item_text: str,
    assistant_fallback_text: str,
) -> str:
    return prompt_turn_runtime_service.preferred_assistant_turn_text(
        turn_events=turn_events,
        assistant_history_text=assistant_history_text,
        response_item_text=response_item_text,
        assistant_fallback_text=assistant_fallback_text,
    )


def _planner_conversation_input_items(self: Any) -> list[dict[str, Any]]:
    return prompt_turn_runtime_service.planner_conversation_input_items(self)


def _planner_history(self: Any) -> list[dict[str, str]]:
    return prompt_turn_runtime_service.planner_history(self)


def _turn_used_provider(turn: dict[str, Any]) -> bool:
    return prompt_turn_runtime_service.turn_used_provider(turn)


def _planner_environment_context_items(
    self: Any,
    *,
    snapshot_override: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    return planner_context_runtime_service.planner_environment_context_items(
        self,
        snapshot_override=snapshot_override,
    )


def _planner_workspace_context_items(
    self: Any,
    *,
    snapshot_override: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    return planner_context_runtime_service.planner_workspace_context_items(
        self,
        snapshot_override=snapshot_override,
    )


def _planner_history_with_context_updates(
    self: Any,
    *,
    planner_history: list[dict[str, str]] | None = None,
    environment_snapshot: dict[str, Any] | None = None,
    workspace_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    return planner_context_runtime_service.planner_history_with_context_updates(
        self,
        planner_history=planner_history,
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
    )


def _turn_context_rollout_items(
    self: Any,
    *,
    pending_environment_messages: list[dict[str, str]],
    pending_context_messages: list[dict[str, str]],
    pending_context_items: list[ReferenceContextItem],
    next_environment_snapshot: dict[str, Any],
    next_workspace_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    return prompt_turn_runtime_service.turn_context_rollout_items(
        self,
        pending_environment_messages=pending_environment_messages,
        pending_context_messages=pending_context_messages,
        pending_context_items=pending_context_items,
        next_environment_snapshot=next_environment_snapshot,
        next_workspace_snapshot=next_workspace_snapshot,
    )


def _append_context_history_item(self: Any, target: str, item: dict[str, str]) -> None:
    prompt_turn_runtime_service.append_context_history_item(self, target, item)


def _append_reference_context_item(self: Any, item: dict[str, Any]) -> None:
    prompt_turn_runtime_service.append_reference_context_item(self, item)


def _append_history_turn(self: Any, turn: dict[str, Any]) -> None:
    prompt_turn_runtime_service.append_history_turn(self, turn)


def _apply_turn_context_updates(
    self: Any,
    *,
    pending_environment_messages: list[dict[str, str]],
    pending_context_messages: list[dict[str, str]],
    pending_context_items: list[ReferenceContextItem],
    next_environment_snapshot: dict[str, Any],
    next_workspace_snapshot: dict[str, Any],
) -> None:
    prompt_turn_runtime_service.apply_turn_context_updates(
        self,
        pending_environment_messages=pending_environment_messages,
        pending_context_messages=pending_context_messages,
        pending_context_items=pending_context_items,
        next_environment_snapshot=next_environment_snapshot,
        next_workspace_snapshot=next_workspace_snapshot,
    )


def bind_runtime_prompt_context_methods(runtime_cls: Any) -> None:
    runtime_cls._environment_context_turn_update = _environment_context_turn_update
    runtime_cls._workspace_context_turn_update = _workspace_context_turn_update
    runtime_cls._planner_message_input_item = staticmethod(_planner_message_input_item)
    runtime_cls._workspace_snapshot_has_context = staticmethod(_workspace_snapshot_has_context)
    runtime_cls._planner_message_history_input_items = _planner_message_history_input_items
    runtime_cls._planner_context_input_items = _planner_context_input_items
    runtime_cls._merge_protocol_diagnostics = staticmethod(_merge_protocol_diagnostics)
    runtime_cls._request_contract_payload = _request_contract_payload
    runtime_cls._planner_base_history_input_items = _planner_base_history_input_items
    runtime_cls._planner_developer_input_item = staticmethod(_planner_developer_input_item)
    runtime_cls._planner_turn_context_replay_items = _planner_turn_context_replay_items
    runtime_cls._planner_turn_response_replay_items = _planner_turn_response_replay_items
    runtime_cls._planner_conversation_rollout_items = _planner_conversation_rollout_items
    runtime_cls._planner_conversation_turn_items = _planner_conversation_turn_items
    runtime_cls._planner_conversation_item_count = _planner_conversation_item_count
    runtime_cls._history_summary_text_for_turn = _history_summary_text_for_turn
    runtime_cls._build_auto_compaction_replacement_history = (
        _build_auto_compaction_replacement_history
    )
    runtime_cls._apply_compaction_state = _apply_compaction_state
    runtime_cls._maybe_auto_compact_history = _maybe_auto_compact_history
    runtime_cls._compact_history = _compact_history
    runtime_cls._planner_history_input_items = _planner_history_input_items
    runtime_cls._normalized_planner_input_item = _normalized_planner_input_item
    runtime_cls._assistant_text_from_turn_events = staticmethod(_assistant_text_from_turn_events)
    runtime_cls._turn_events_have_structured_tool_items = staticmethod(
        _turn_events_have_structured_tool_items
    )
    runtime_cls._turn_replay_requires_structured_tool_output = staticmethod(
        _turn_replay_requires_structured_tool_output
    )
    runtime_cls._response_items_with_canonical_final_message = classmethod(
        _response_items_with_canonical_final_message
    )
    runtime_cls._preferred_assistant_turn_text = classmethod(_preferred_assistant_turn_text)
    runtime_cls._planner_conversation_input_items = _planner_conversation_input_items
    runtime_cls._planner_history = _planner_history
    runtime_cls._turn_used_provider = staticmethod(_turn_used_provider)
    runtime_cls._planner_environment_context_items = _planner_environment_context_items
    runtime_cls._planner_workspace_context_items = _planner_workspace_context_items
    runtime_cls._planner_history_with_context_updates = _planner_history_with_context_updates
    runtime_cls._turn_context_rollout_items = _turn_context_rollout_items
    runtime_cls._append_context_history_item = _append_context_history_item
    runtime_cls._append_reference_context_item = _append_reference_context_item
    runtime_cls._append_history_turn = _append_history_turn
    runtime_cls._apply_turn_context_updates = _apply_turn_context_updates
