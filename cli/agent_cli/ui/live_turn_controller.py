from __future__ import annotations

import threading
from datetime import datetime
from time import monotonic

from textual.css.query import NoMatches

from cli.agent_cli.models import (
    REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
    ActivityEvent,
)
from cli.agent_cli.ui import live_turn_controller_helpers as live_turn_controller_helpers_service
from cli.agent_cli.ui import (
    live_turn_controller_normalization_helpers as live_turn_controller_normalization_helpers_service,
)
from cli.agent_cli.ui import (
    live_turn_controller_projection_helpers as live_turn_controller_projection_helpers_service,
)
from cli.agent_cli.ui import (
    live_turn_controller_pure_helpers as live_turn_controller_pure_helpers_service,
)
from cli.agent_cli.ui.transcript_history import TranscriptEntry, render_transcript_entries


class LiveTurnControllerMixin:
    _COMPLETION_TIME_PREFIX = "🏁 "
    _ASCII_COMPLETION_TIME_PREFIX = "T "
    _LEGACY_ASCII_COMPLETION_TIME_PREFIX = "t "
    _COMPLETION_ELAPSED_PREFIX = "⌛"
    _LEGACY_COMPLETION_TIME_PREFIX = "完成时间 "

    @staticmethod
    def _interrupt_terminal_activity_key() -> str:
        return "interrupt:terminal"

    def _note_work_activity_from_activity(self, event: ActivityEvent | None) -> None:
        if event is None:
            return
        if event.kind in {"tool", "command", "web", "browser"}:
            self._live_turn_had_work_activity = True

    def _note_work_activity_from_turn_item(self, item: dict[str, object] | None) -> None:
        if not isinstance(item, dict):
            return
        if str(item.get("type") or "").strip() in {
            "command_execution",
            "mcp_tool_call",
            "todo_list",
        }:
            self._live_turn_had_work_activity = True

    @staticmethod
    def _agent_message_phase(item: dict[str, object]) -> str:
        return live_turn_controller_helpers_service.agent_message_phase(item)

    def _final_separator_label(self) -> str:
        return live_turn_controller_helpers_service.final_separator_label(
            t_fn=self._t,
            completion_time=self._completion_time_text(),
            elapsed=self._completion_elapsed_text(),
        )

    def _should_insert_final_separator(self, entry: TranscriptEntry) -> bool:
        return live_turn_controller_helpers_service.should_insert_final_separator(
            entry=entry,
            transcript_entries=self._transcript_entries,
            live_turn_had_work_activity=self._live_turn_had_work_activity,
            live_turn_final_separator_emitted=self._live_turn_final_separator_emitted,
        )

    def _begin_activity_capture(self) -> None:
        self._transcript_turn_serial += 1
        self._active_transcript_turn_key = f"turn:{self._transcript_turn_serial}"
        self._live_turn_request_is_slash = bool(
            getattr(self, "_active_runtime_request_is_slash", False)
        )
        self._live_activity_signatures = set()
        self._live_turn_event_signatures = set()
        self._live_turn_backfill_counts = {}
        self._live_streamed_texts = set()
        self._live_turn_event_sequence = 0
        self._live_turn_last_tool_sequence = -1
        self._live_turn_last_agent_message_key = None
        self._live_turn_last_agent_message_sequence = -1
        self._live_turn_had_work_activity = False
        self._live_turn_final_separator_emitted = False
        self._live_turn_interrupt_requested = False
        self._live_command_execution_commands = {}
        self._assistant_message_streaming_active = False
        self._busy_status_hidden = False
        self._pending_status_indicator_restore = False

    def _mark_live_turn_interrupt_requested(self) -> None:
        self._live_turn_interrupt_requested = True
        self._drop_live_turn_todo_entries()

    def _render_live_interrupt_notice(self) -> None:
        self._write_live_turn_event(
            {
                "type": "item.completed",
                "item": {
                    "id": self._interrupt_terminal_activity_key(),
                    "type": "agent_message",
                    "text": REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
                },
            }
        )

    def _drop_live_turn_todo_entries(self) -> None:
        compacted_entries = (
            live_turn_controller_projection_helpers_service.drop_live_turn_todo_entries(
                self._transcript_entries,
                active_transcript_turn_key=self._active_transcript_turn_key,
            )
        )
        if compacted_entries is None:
            return
        self._transcript_entries = compacted_entries
        self._transcript_lines = render_transcript_entries(self._transcript_entries)
        try:
            self._sync_transcript()
        except NoMatches:
            return

    def _demote_last_agent_message_before_late_tool(self) -> None:
        activity_key = str(self._live_turn_last_agent_message_key or "").strip()
        if not activity_key:
            return
        update = live_turn_controller_projection_helpers_service.demote_final_agent_message_before_late_tool(
            self._transcript_entries,
            activity_key=activity_key,
        )
        if update is None:
            return
        self._transcript_entries = update.entries
        if update.separator_removed:
            self._live_turn_final_separator_emitted = False
        self._transcript_lines = render_transcript_entries(self._transcript_entries)

    @staticmethod
    def _is_interrupt_terminal_message(text: str) -> bool:
        return live_turn_controller_helpers_service.is_interrupt_terminal_message(text)

    def _should_suppress_turn_event_after_interrupt(self, event: dict[str, object]) -> bool:
        return live_turn_controller_helpers_service.should_suppress_turn_event_after_interrupt(
            event,
            live_turn_interrupt_requested=self._live_turn_interrupt_requested,
            is_interrupt_terminal_message_fn=self._is_interrupt_terminal_message,
        )

    def _on_runtime_activity(self, event: ActivityEvent) -> None:
        if bool(getattr(self, "_shutdown_initiated", False)):
            return
        if getattr(self, "_thread_id", None) == threading.get_ident():
            self._write_live_activity_event(event)
            return
        self.call_from_thread(self._write_live_activity_event, event)

    def _on_runtime_turn_event(self, event: dict[str, object]) -> None:
        if bool(getattr(self, "_shutdown_initiated", False)):
            return
        if getattr(self, "_thread_id", None) == threading.get_ident():
            self._write_live_turn_event(event)
            return
        self.call_from_thread(self._write_live_turn_event, event)

    def _write_live_activity_event(self, event: ActivityEvent) -> None:
        if self._should_suppress_live_activity_event(event):
            return
        signature = self._activity_signature(event)
        if signature in self._live_activity_signatures:
            return
        self._live_activity_signatures.add(signature)
        self._note_work_activity_from_activity(event)
        self._update_busy_status_from_activity(event)
        try:
            self._write_activity_event(event)
        except NoMatches:
            return

    def _should_suppress_live_activity_event(self, event: ActivityEvent) -> bool:
        return live_turn_controller_helpers_service.should_suppress_live_activity_event(
            event,
            live_turn_interrupt_requested=self._live_turn_interrupt_requested,
            live_turn_event_sequence=self._live_turn_event_sequence,
        )

    def _update_busy_status_from_activity(self, event: ActivityEvent) -> None:
        if not self._busy:
            return
        if event.kind == "interrupt":
            self._busy_status_label = self._t("status.interrupting")
            self._refresh_dynamic_hint()
            return
        if event.status == "error":
            return
        summary = live_turn_controller_helpers_service.running_activity_label(
            event,
            format_activity_summary_fn=self._format_activity_summary,
        ).strip()
        if summary:
            self._busy_status_label = summary
            self._refresh_dynamic_hint()

    def _update_busy_status_from_reasoning_item(self, item: dict[str, object]) -> None:
        if not self._busy:
            return
        if str(item.get("type") or "").strip() != "reasoning":
            return
        header = self._extract_first_bold(str(item.get("text") or ""))
        if not header:
            return
        self._busy_status_label = header
        self._refresh_dynamic_hint()

    def _update_streaming_status_from_turn_item(
        self, event_type: str, item: dict[str, object]
    ) -> None:
        if str(item.get("type") or "").strip() != "agent_message":
            return
        if event_type == "item.updated":
            if not self._assistant_message_streaming_active:
                self._assistant_message_streaming_active = True
            self._busy_status_hidden = True
            self._pending_status_indicator_restore = False
            self._refresh_dynamic_hint()
            return
        if event_type == "item.completed":
            had_streaming = self._assistant_message_streaming_active
            self._assistant_message_streaming_active = False
            if not had_streaming:
                return
            if self._agent_message_phase(item) == "commentary":
                self._busy_status_hidden = False
                self._pending_status_indicator_restore = True
                self._maybe_restore_busy_status_indicator()
                return
            self._busy_status_hidden = True
            self._pending_status_indicator_restore = False
            self._refresh_dynamic_hint()

    @classmethod
    def _turn_event_signature(cls, event: dict[str, object]) -> str:
        return live_turn_controller_normalization_helpers_service.turn_event_signature(
            event,
            backfill_signature_fn=cls._turn_event_backfill_signature,
        )

    @classmethod
    def _normalized_turn_event_value(cls, value: object) -> object:
        return live_turn_controller_normalization_helpers_service.normalized_turn_event_value(value)

    @classmethod
    def _turn_event_backfill_signature(cls, event: dict[str, object]) -> str:
        return live_turn_controller_normalization_helpers_service.turn_event_backfill_signature(
            event
        )

    def _write_live_turn_event(self, event: dict[str, object]) -> None:
        event_type = str(event.get("type") or "").strip()
        if event_type == "provider.retry":
            message = str(event.get("message") or "").strip()
            if message:
                self._busy_status_label = message
                self._busy_status_hidden = False
                self._pending_status_indicator_restore = False
                self._refresh_dynamic_hint()
            return
        if event_type in {"turn.completed", "turn.failed"}:
            self._assistant_message_streaming_active = False
            self._refresh_dynamic_hint()
            self._finalize_live_turn_items()
            return
        if self._should_suppress_turn_event_after_interrupt(event):
            return
        self._live_turn_event_sequence += 1
        signature = self._turn_event_signature(event)
        if signature in self._live_turn_event_signatures:
            return
        self._live_turn_event_signatures.add(signature)
        semantic_signature = self._turn_event_backfill_signature(event)
        self._live_turn_backfill_counts[semantic_signature] = (
            self._live_turn_backfill_counts.get(semantic_signature, 0) + 1
        )
        activity = self._turn_event_activity(event)
        if activity is not None:
            activity_signature = self._activity_signature(activity)
            if activity_signature in self._live_activity_signatures:
                return
            self._live_activity_signatures.add(activity_signature)
            self._note_work_activity_from_activity(activity)
            self._note_pending_approval_activity(activity)
            self._update_busy_status_from_activity(activity)
        item = event.get("item")
        if isinstance(item, dict):
            self._update_streaming_status_from_turn_item(event_type, item)
            self._note_work_activity_from_turn_item(item)
            self._update_busy_status_from_reasoning_item(item)
        entry = self._turn_event_entry(event, activity=activity)
        if entry is None:
            return
        item_projection = None
        if isinstance(item, dict):
            item_projection = (
                live_turn_controller_projection_helpers_service.project_live_turn_item(
                    item=item,
                    event_type=event_type,
                    live_turn_event_sequence=self._live_turn_event_sequence,
                    entry_activity_key=entry.activity_key,
                )
            )
            if item_projection.tool_sequence is not None:
                self._demote_last_agent_message_before_late_tool()
                self._live_turn_last_tool_sequence = item_projection.tool_sequence
                self._note_work_activity_from_turn_item(item)
        try:
            self._append_transcript_entry(entry, leading_blank=not bool(entry.activity_key))
        except NoMatches:
            return
        if item_projection is not None:
            if item_projection.completed_text:
                self._live_streamed_texts.add(item_projection.completed_text)
            if item_projection.has_completed_agent_message:
                self._live_turn_last_agent_message_key = item_projection.completed_agent_message_key
                self._live_turn_last_agent_message_sequence = (
                    item_projection.completed_agent_message_sequence
                )

    def _finalize_live_turn_items(self) -> None:
        activity_key = str(self._live_turn_last_agent_message_key or "").strip()
        if not live_turn_controller_projection_helpers_service.should_finalize_live_turn_items(
            activity_key,
            live_turn_last_tool_sequence=self._live_turn_last_tool_sequence,
            live_turn_last_agent_message_sequence=self._live_turn_last_agent_message_sequence,
        ):
            return
        finalized_entry_update = (
            live_turn_controller_projection_helpers_service.finalized_live_turn_entry_update(
                self._transcript_entries,
                activity_key=activity_key,
                is_interrupt_terminal_message_fn=self._is_interrupt_terminal_message,
                format_transcript_block_fn=self._format_transcript_block,
            )
        )
        if finalized_entry_update is None:
            return
        index, finalized_entry = finalized_entry_update
        self._transcript_entries[index] = finalized_entry
        self._transcript_lines = render_transcript_entries(self._transcript_entries)
        try:
            self._sync_transcript()
        except NoMatches:
            pass

    @classmethod
    def _entry_has_completion_time(cls, content: str) -> bool:
        return live_turn_controller_pure_helpers_service.entry_has_completion_time(
            content,
            completion_time_prefixes=(
                cls._COMPLETION_TIME_PREFIX,
                cls._ASCII_COMPLETION_TIME_PREFIX,
                cls._LEGACY_ASCII_COMPLETION_TIME_PREFIX,
            ),
            completion_elapsed_prefix=cls._COMPLETION_ELAPSED_PREFIX,
            legacy_completion_time_prefix=cls._LEGACY_COMPLETION_TIME_PREFIX,
            is_hhmm_timestamp_fn=cls._is_hhmm_timestamp,
        )

    @staticmethod
    def _is_hhmm_timestamp(timestamp_text: str) -> bool:
        return live_turn_controller_pure_helpers_service.is_hhmm_timestamp(timestamp_text)

    def _completion_elapsed_seconds(self) -> int:
        return live_turn_controller_pure_helpers_service.completion_elapsed_seconds(
            self._busy_started_at,
            now_monotonic=monotonic(),
        )

    def _completion_elapsed_text(self) -> str:
        return live_turn_controller_pure_helpers_service.completion_elapsed_text(
            self._completion_elapsed_seconds()
        )

    def _completion_time_text(self) -> str:
        return live_turn_controller_pure_helpers_service.completion_time_text(datetime.now())

    @staticmethod
    def _turn_event_item_key(item: dict[str, object]) -> str | None:
        return live_turn_controller_helpers_service.turn_event_item_key(item)

    @staticmethod
    def _extract_first_bold(text: str) -> str | None:
        return live_turn_controller_helpers_service.extract_first_bold(text)

    @classmethod
    def _reasoning_summary_text(cls, text: str) -> str:
        return live_turn_controller_helpers_service.reasoning_summary_text(text)
