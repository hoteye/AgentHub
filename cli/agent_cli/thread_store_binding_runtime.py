from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from cli.agent_cli import thread_store_helpers_runtime as helper_runtime
from cli.agent_cli import thread_store_projection_runtime as projection_runtime
from cli.agent_cli import thread_store_replay as replay_helpers
from cli.agent_cli import thread_store_runtime as thread_store_runtime_service
from cli.agent_cli import thread_store_serialization as serialization_helpers
from cli.agent_cli import thread_store_transactions as transaction_helpers
from cli.agent_cli.models import (
    ActivityEvent,
    PromptAttachment,
    PromptResponse,
    ReferenceContextItem,
    ResponseInputItem,
    ThreadHistoryTurn,
    TurnContextRollout,
    ToolEvent,
)


def install_thread_store_bindings(thread_store_cls: type[Any], *, record_cls: type[Any], utc_now_fn: Any) -> None:
    thread_store_cls._attachment_to_dict = staticmethod(PromptAttachment.to_dict)
    thread_store_cls._reference_context_item_to_dict = staticmethod(ReferenceContextItem.to_dict)
    thread_store_cls._tool_event_to_dict = staticmethod(ToolEvent.to_dict)
    thread_store_cls._activity_event_to_dict = staticmethod(ActivityEvent.to_dict)
    thread_store_cls._history_item_from_rollout_payload = staticmethod(replay_helpers.history_item_from_rollout_payload)
    thread_store_cls._response_input_item_from_rollout_payload = staticmethod(
        replay_helpers.response_input_item_from_rollout_payload
    )
    thread_store_cls._reference_context_item_from_rollout_payload = staticmethod(
        replay_helpers.reference_context_item_from_rollout_payload
    )
    thread_store_cls._state_snapshot_from_rollout_payload = staticmethod(replay_helpers.state_snapshot_from_rollout_payload)
    thread_store_cls._rollback_turn_count = staticmethod(replay_helpers.rollback_turn_count)
    thread_store_cls._tool_item_events_from_turn_events = staticmethod(replay_helpers.tool_item_events_from_turn_events)
    thread_store_cls._assistant_text_from_turn_events = staticmethod(replay_helpers.assistant_text_from_turn_events)
    thread_store_cls._planner_developer_input_item = staticmethod(replay_helpers.planner_developer_input_item)
    thread_store_cls._iso_to_unix_seconds = staticmethod(helper_runtime.iso_to_unix_seconds)
    thread_store_cls._path_mtime_iso = staticmethod(transaction_helpers.path_mtime_iso)

    def _row_to_record(row: sqlite3.Row) -> Any:
        return helper_runtime.row_to_record(row, record_cls=record_cls)

    def _derive_name(user_text: str) -> str:
        return helper_runtime.derive_name(user_text)

    def _dedupe_reference_context_items(items: list[ReferenceContextItem]) -> list[ReferenceContextItem]:
        return serialization_helpers.dedupe_reference_context_items(items)

    def _reference_context_items_from_tool_event(event: ToolEvent) -> list[ReferenceContextItem]:
        return serialization_helpers.reference_context_items_from_tool_event(event)

    def _history_item_from_planner_input_item(
        cls: type[Any], payload: dict[str, Any]
    ) -> dict[str, str] | None:
        return replay_helpers.history_item_from_planner_input_item(payload)

    def _compacted_replacement_history(
        cls: type[Any],
        payload: dict[str, Any],
        *,
        existing_history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        return replay_helpers.compacted_replacement_history(payload, existing_history=existing_history)

    def _turn_has_structured_tool_items(cls: type[Any], turn: ThreadHistoryTurn) -> bool:
        return replay_helpers.turn_has_structured_tool_items(turn)

    def _turn_has_tool_history(cls: type[Any], turn: ThreadHistoryTurn) -> bool:
        return replay_helpers.turn_has_tool_history(turn)

    def _turn_replay_requires_structured_tool_output(turn: ThreadHistoryTurn) -> bool:
        return helper_runtime.turn_replay_requires_structured_tool_output(turn)

    def _response_items_with_canonical_final_message(
        cls: type[Any],
        response_items: list[dict[str, Any]],
        turn_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return thread_store_runtime_service.response_items_with_canonical_final_message(response_items, turn_events)

    def _preferred_assistant_turn_text(
        cls: type[Any],
        turn: ThreadHistoryTurn,
        *,
        include_response_items: bool = True,
    ) -> str:
        return replay_helpers.preferred_assistant_turn_text(turn, include_response_items=include_response_items)

    def _history_from_turns(turns: list[ThreadHistoryTurn]) -> list[dict[str, str]]:
        return replay_helpers.history_from_turns(turns)

    def _planner_history_from_turns(
        cls: type[Any],
        turns: list[ThreadHistoryTurn],
        *,
        fallback_history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        return projection_runtime.planner_history_from_turns(
            turns,
            fallback_history=fallback_history,
            planner_history_limit=cls._PLANNER_HISTORY_LIMIT_MESSAGES,
        )

    def _planner_input_items_from_history(
        cls: type[Any], history: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        return projection_runtime.planner_input_items_from_history(
            history,
            planner_history_limit=cls._PLANNER_HISTORY_LIMIT_MESSAGES,
        )

    def _planner_turn_context_replay_items(
        cls: type[Any], turn_context: TurnContextRollout | None
    ) -> list[dict[str, Any]]:
        return replay_helpers.planner_turn_context_replay_items(turn_context)

    def _planner_turn_response_replay_items(
        cls: type[Any], turn: ThreadHistoryTurn
    ) -> list[dict[str, Any]]:
        return replay_helpers.planner_turn_response_replay_items(turn)

    def _planner_input_items_from_turns(
        cls: type[Any],
        turns: list[ThreadHistoryTurn],
        *,
        fallback_history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        return projection_runtime.planner_input_items_from_turns(
            turns,
            fallback_history=fallback_history,
            planner_history_limit=cls._PLANNER_HISTORY_LIMIT_MESSAGES,
            turn_used_provider_fn=cls._turn_used_provider,
        )

    def _planner_input_items_from_rollout_items(
        cls: type[Any],
        rollout_items: list[dict[str, Any]],
        *,
        fallback_history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        return projection_runtime.planner_input_items_from_rollout_items(
            rollout_items,
            fallback_history=fallback_history,
            planner_history_limit=cls._PLANNER_HISTORY_LIMIT_MESSAGES,
            turn_used_provider_fn=cls._turn_used_provider,
        )

    def _context_items_from_turns(cls: type[Any], turns: list[ThreadHistoryTurn]) -> list[ReferenceContextItem]:
        return helper_runtime.context_items_from_turns(
            turns,
            dedupe_reference_context_items_fn=cls._dedupe_reference_context_items,
        )

    def _state_from_turns(turns: list[ThreadHistoryTurn]) -> dict[str, Any]:
        return helper_runtime.state_from_turns(turns)

    def _turn_used_provider(turn: ThreadHistoryTurn) -> bool:
        return projection_runtime.turn_used_provider(
            turn,
            turn_has_structured_tool_items_fn=thread_store_cls._turn_has_structured_tool_items,
        )

    def _drop_last_n_user_turns(turns: list[ThreadHistoryTurn], num_turns: int) -> list[ThreadHistoryTurn]:
        return helper_runtime.drop_last_n_user_turns(turns, num_turns)

    def _canonical_turn_events(
        response: PromptResponse,
        *,
        response_items: list[ResponseInputItem],
    ) -> list[dict[str, Any]]:
        return helper_runtime.canonical_turn_events(response, response_items=response_items)

    def _thread_meta_from_rollout_path(cls: type[Any], rollout_path: Path) -> Any:
        return transaction_helpers.thread_meta_from_rollout_path(rollout_path, record_cls=record_cls)

    def _thread_rollout_summary(cls: type[Any], rollout_path: Path) -> dict[str, Any]:
        return transaction_helpers.thread_rollout_summary(cls, rollout_path)

    def _name_from_history(cls: type[Any], history: list[dict[str, Any]]) -> str:
        return replay_helpers.name_from_history(history, derive_name=cls._derive_name)

    def _response_item_seed_from_history(
        cls: type[Any], item: dict[str, Any]
    ) -> dict[str, Any] | None:
        return replay_helpers.response_item_seed_from_history(item)

    def _rollout_seed_items_from_history(
        cls: type[Any], history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return replay_helpers.rollout_seed_items_from_history(history, now_iso_fn=utc_now_fn)

    thread_store_cls._row_to_record = staticmethod(_row_to_record)
    thread_store_cls._derive_name = staticmethod(_derive_name)
    thread_store_cls._dedupe_reference_context_items = staticmethod(_dedupe_reference_context_items)
    thread_store_cls._reference_context_items_from_tool_event = staticmethod(_reference_context_items_from_tool_event)
    thread_store_cls._history_item_from_planner_input_item = classmethod(_history_item_from_planner_input_item)
    thread_store_cls._compacted_replacement_history = classmethod(_compacted_replacement_history)
    thread_store_cls._turn_has_structured_tool_items = classmethod(_turn_has_structured_tool_items)
    thread_store_cls._turn_has_tool_history = classmethod(_turn_has_tool_history)
    thread_store_cls._turn_replay_requires_structured_tool_output = staticmethod(_turn_replay_requires_structured_tool_output)
    thread_store_cls._response_items_with_canonical_final_message = classmethod(
        _response_items_with_canonical_final_message
    )
    thread_store_cls._preferred_assistant_turn_text = classmethod(_preferred_assistant_turn_text)
    thread_store_cls._history_from_turns = staticmethod(_history_from_turns)
    thread_store_cls._planner_history_from_turns = classmethod(_planner_history_from_turns)
    thread_store_cls._planner_input_items_from_history = classmethod(_planner_input_items_from_history)
    thread_store_cls._planner_turn_context_replay_items = classmethod(_planner_turn_context_replay_items)
    thread_store_cls._planner_turn_response_replay_items = classmethod(_planner_turn_response_replay_items)
    thread_store_cls._planner_input_items_from_turns = classmethod(_planner_input_items_from_turns)
    thread_store_cls._planner_input_items_from_rollout_items = classmethod(_planner_input_items_from_rollout_items)
    thread_store_cls._context_items_from_turns = classmethod(_context_items_from_turns)
    thread_store_cls._state_from_turns = staticmethod(_state_from_turns)
    thread_store_cls._turn_used_provider = staticmethod(_turn_used_provider)
    thread_store_cls._drop_last_n_user_turns = staticmethod(_drop_last_n_user_turns)
    thread_store_cls._canonical_turn_events = staticmethod(_canonical_turn_events)
    thread_store_cls._thread_meta_from_rollout_path = classmethod(_thread_meta_from_rollout_path)
    thread_store_cls._thread_rollout_summary = classmethod(_thread_rollout_summary)
    thread_store_cls._name_from_history = classmethod(_name_from_history)
    thread_store_cls._response_item_seed_from_history = classmethod(_response_item_seed_from_history)
    thread_store_cls._rollout_seed_items_from_history = classmethod(_rollout_seed_items_from_history)
