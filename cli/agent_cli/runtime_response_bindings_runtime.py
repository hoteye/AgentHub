from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from cli.agent_cli.models import (
    ActivityEvent,
    PromptAttachment,
    PromptResponse,
    ReferenceContextItem,
    ResponseInputItem,
    ToolEvent,
)
from cli.agent_cli.runtime_services import prompt_turn_runtime as prompt_turn_runtime_service
from cli.agent_cli.runtime_services import runtime_context_runtime as runtime_context_runtime_service
from cli.agent_cli.runtime_services import runtime_response_runtime as runtime_response_runtime_service


def _next_item_index(item_events: List[Dict[str, Any]]) -> int:
    return runtime_response_runtime_service.next_item_index(item_events)


def _turn_events_from_item_events(
    cls: Any,
    *,
    assistant_text: str,
    response_items: Optional[List[ResponseInputItem]] = None,
    item_events: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    return runtime_response_runtime_service.turn_events_from_item_events(
        assistant_text=str(assistant_text or ""),
        response_items=response_items,
        item_events=item_events,
    )


def _build_response(
    self: Any,
    *,
    user_text: str,
    assistant_text: str,
    command_display_text: str = "",
    commentary_text: str = "",
    response_items: Optional[List[ResponseInputItem]] = None,
    attachments: List[PromptAttachment],
    reference_context_items: Optional[List[ReferenceContextItem]] = None,
    tool_events: List[ToolEvent],
    extra_activity_events: Optional[List[ActivityEvent]] = None,
    protocol_diagnostics: Optional[Dict[str, Any]] = None,
    source_text: str,
    handled_as_command: bool,
    plan: Optional[Dict[str, Any]] = None,
    timings: Optional[Dict[str, Any]] = None,
    turn_events: Optional[List[Dict[str, Any]]] = None,
) -> PromptResponse:
    return runtime_response_runtime_service.build_response(
        self,
        user_text=user_text,
        assistant_text=assistant_text,
        command_display_text=command_display_text,
        commentary_text=commentary_text,
        response_items=response_items,
        attachments=attachments,
        reference_context_items=reference_context_items,
        tool_events=tool_events,
        extra_activity_events=extra_activity_events,
        protocol_diagnostics=protocol_diagnostics,
        source_text=source_text,
        handled_as_command=handled_as_command,
        plan=plan,
        timings=timings,
        turn_events=turn_events,
    )


def _legacy_handle_prompt(self: Any, text: str) -> PromptResponse:
    return self.handle_prompt(text)


def _build_activity_events(
    self: Any,
    *,
    source_text: str,
    tool_events: List[ToolEvent],
    handled_as_command: bool,
    plan: Optional[Dict[str, Any]] = None,
) -> List[ActivityEvent]:
    return runtime_response_runtime_service.build_activity_events(
        self,
        source_text=source_text,
        tool_events=tool_events,
        handled_as_command=handled_as_command,
        plan=plan,
    )


def _activity_events_for_tool_event(self: Any, event: ToolEvent) -> List[ActivityEvent]:
    return runtime_response_runtime_service.activity_events_for_tool_event(self, event)


def _activity_detail_for_event(self: Any, event: ToolEvent) -> str:
    return runtime_response_runtime_service.activity_detail_for_event(event)


def _detail_for_event(event: ToolEvent) -> str:
    return runtime_response_runtime_service.detail_for_event(event)


def _apply_tool_state(self: Any, event: ToolEvent) -> None:
    runtime_response_runtime_service.apply_tool_state(self, event)


def _build_status(
    self: Any,
    source_text: str,
    events: List[ToolEvent],
    *,
    timings: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    return runtime_response_runtime_service.build_status(self, source_text, events, timings=timings)


def _snapshot_thread_state(self: Any) -> Dict[str, Any]:
    return runtime_response_runtime_service.snapshot_thread_state(self)


def _normalized_history_item(item: Any) -> Optional[Dict[str, str]]:
    return runtime_context_runtime_service.normalized_history_item(item)


def _restore_workspace_context_state(
    self: Any,
    state: Dict[str, Any],
    context_items: Optional[List[Dict[str, Any]]] = None,
) -> None:
    runtime_context_runtime_service.restore_workspace_context_state(self, state, context_items)


def _restore_environment_context_state(self: Any, state: Dict[str, Any]) -> None:
    runtime_context_runtime_service.restore_environment_context_state(self, state)


def _restore_memory_context_state(self: Any, state: Dict[str, Any]) -> None:
    runtime_context_runtime_service.restore_memory_context_state(self, state)


def _restore_file_read_guard_state(self: Any, state: Dict[str, Any]) -> None:
    runtime_context_runtime_service.restore_file_read_guard_state(self, state)


def _current_datetime(self: Any) -> datetime:
    return runtime_context_runtime_service.current_datetime(self)


def _subagent_context_text(self: Any) -> str | None:
    return runtime_context_runtime_service.subagent_context_text(self)


def _delegated_planner_input_items(self: Any) -> List[Dict[str, Any]]:
    return runtime_context_runtime_service.delegated_planner_input_items(self)


def handle_prompt(self: Any, text: str, *, attachments: Optional[List[PromptAttachment]] = None) -> PromptResponse:
    return prompt_turn_runtime_service.handle_prompt(
        self,
        text,
        attachments=attachments,
    )


def _append_history(self: Any, role: str, content: str) -> None:
    prompt_turn_runtime_service.append_history(self, role, content)


def _append_rollout_item(self: Any, payload: Dict[str, Any]) -> None:
    prompt_turn_runtime_service.append_rollout_item(self, payload)


def bind_runtime_response_methods(runtime_cls: Any) -> None:
    runtime_cls._next_item_index = staticmethod(_next_item_index)
    runtime_cls._turn_events_from_item_events = classmethod(_turn_events_from_item_events)
    runtime_cls._build_response = _build_response
    runtime_cls._legacy_handle_prompt = _legacy_handle_prompt
    runtime_cls._build_activity_events = _build_activity_events
    runtime_cls._activity_events_for_tool_event = _activity_events_for_tool_event
    runtime_cls._activity_detail_for_event = _activity_detail_for_event
    runtime_cls._detail_for_event = staticmethod(_detail_for_event)
    runtime_cls._apply_tool_state = _apply_tool_state
    runtime_cls._build_status = _build_status
    runtime_cls._snapshot_thread_state = _snapshot_thread_state
    runtime_cls._normalized_history_item = staticmethod(_normalized_history_item)
    runtime_cls._restore_workspace_context_state = _restore_workspace_context_state
    runtime_cls._restore_environment_context_state = _restore_environment_context_state
    runtime_cls._restore_memory_context_state = _restore_memory_context_state
    runtime_cls._restore_file_read_guard_state = _restore_file_read_guard_state
    runtime_cls._current_datetime = _current_datetime
    runtime_cls._subagent_context_text = _subagent_context_text
    runtime_cls._delegated_planner_input_items = _delegated_planner_input_items
    runtime_cls.handle_prompt = handle_prompt
    runtime_cls._append_history = _append_history
    runtime_cls._append_rollout_item = _append_rollout_item
