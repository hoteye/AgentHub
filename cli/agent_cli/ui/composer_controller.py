from __future__ import annotations

from typing import TYPE_CHECKING

from textual.css.query import NoMatches

from cli.agent_cli.models import PromptAttachment
from cli.agent_cli.slash_commands import slash_command_available_during_busy
from cli.agent_cli.startup_debug import startup_log
from cli.agent_cli.ui.attachments import (
    extract_attachment_references,
    format_attachment_reference,
    format_pasted_path,
    normalize_pasted_path_text,
    normalize_single_pasted_path,
)
from cli.agent_cli.ui.composer import PromptComposer
from cli.agent_cli.ui.paste_pipeline import (
    expand_pending_pastes,
    insert_paste_text,
    next_large_paste_placeholder,
    prepare_prompt_submission,
    read_clipboard_text,
    retain_pending_pastes_for_text,
)

if TYPE_CHECKING:
    from textual.events import MouseMove, MouseUp


class ComposerControllerMixin:
    _BUSY_SLASH_COMMAND_NOTICE = "Slash commands are unavailable while a task is in progress."

    @staticmethod
    def _normalize_exit_alias(text: str) -> str:
        normalized = str(text or "").strip()
        return "/exit" if normalized in {"exit", "quit"} else text

    @staticmethod
    def _slash_command_available_during_busy(text_or_name: str) -> bool:
        return slash_command_available_during_busy(text_or_name)

    async def action_submit_prompt(self) -> None:
        await self._submit_prompt(submit_mode="auto")

    async def action_queue_prompt(self) -> None:
        await self._submit_prompt(submit_mode="queue")

    def _queue_prompt_actionable(self, text: str | None = None) -> bool:
        normalized = str(self._current_prompt_text() if text is None else text).strip()
        if not normalized:
            return False
        if not self._has_pending_runtime_work():
            return False
        if normalized.startswith("/") and not self._slash_command_available_during_busy(normalized):
            return False
        return True

    async def _submit_prompt(self, *, submit_mode: str) -> None:
        clear_shortcut_overlay = getattr(self, "_clear_shortcut_overlay", None)
        if callable(clear_shortcut_overlay):
            clear_shortcut_overlay()
        queue_mode = str(submit_mode or "auto").strip().lower() == "queue"
        self._clear_quit_shortcut()
        self._flush_prompt_composer_burst()
        display_text = self._current_prompt_text().strip()
        text, attachments = self._prepare_prompt_submission(display_text)
        text = self._normalize_exit_alias(text)
        display_text = self._normalize_exit_alias(display_text)
        echo_text = self._expand_pending_pastes(display_text).strip()
        actual_chars = len(text)
        if actual_chars > self.MAX_USER_INPUT_TEXT_CHARS:
            self._write_system_notice(self._user_input_too_large_message(actual_chars))
            self._focus_input()
            return
        has_pending_runtime_work = self._has_pending_runtime_work()
        slash_commands_blocked = (
            bool(self._slash_commands_blocked_by_pending_runtime_work())
            if callable(getattr(self, "_slash_commands_blocked_by_pending_runtime_work", None))
            else has_pending_runtime_work
        )
        if (
            text.startswith("/")
            and slash_commands_blocked
            and not self._slash_command_available_during_busy(text)
        ):
            self._write_system_notice(self._BUSY_SLASH_COMMAND_NOTICE)
            self._focus_input()
            return
        self._clear_prompt_text()
        self._refresh_prompt_composer()
        self._force_transcript_follow_bottom()
        if not text:
            self._focus_input()
            return
        queue_after_current_turn = (
            has_pending_runtime_work
            and not text.startswith("/")
            and not bool(getattr(self, "_live_turn_interrupt_requested", False))
        )
        if queue_after_current_turn and not queue_mode and self._runtime_supports_pending_steer():
            steer_result = self.runtime.steer_active_run(text, attachments=attachments)
            if bool(steer_result.get("accepted")):
                self.prompt_count += 1
                self._record_prompt_history(text)
                self._write_user_prompt(echo_text, attachments=attachments)
                self._focus_input()
                return
            if not bool(steer_result.get("fallback_queue")):
                self._focus_input()
                return
        defer_user_echo = (queue_mode or queue_after_current_turn) and has_pending_runtime_work
        self.prompt_count += 1
        self._record_prompt_history(text)
        if not defer_user_echo:
            self._write_user_prompt(echo_text, attachments=attachments)
        if self._handle_local_slash_command(text, attachments=attachments):
            self._focus_input()
            return
        if defer_user_echo:
            await self._enqueue_runtime_request(
                text,
                attachments,
                display_text=echo_text,
                display_attachments=attachments,
                priority="later",
            )
        else:
            await self._enqueue_runtime_request(text, attachments)
        self._focus_input()

    def _runtime_supports_pending_steer(self) -> bool:
        supported = getattr(getattr(self, "runtime", None), "pending_steer_supported", None)
        if not callable(supported):
            return False
        try:
            return bool(supported())
        except Exception:
            return False

    def _force_transcript_follow_bottom(self) -> None:
        for widget_id in ("#main_log", "#transcript_log"):
            try:
                widget = self.query_one(widget_id)
                if hasattr(widget, "_force_follow_bottom"):
                    widget._force_follow_bottom = True
            except Exception:
                pass

    def action_paste_prompt(self) -> None:
        self._clear_quit_shortcut()
        self.paste_prompt_from_clipboard(report_empty=True)

    def action_clear_prompt(self) -> None:
        self._clear_quit_shortcut()
        self._clear_prompt_text()
        self._refresh_prompt_composer()
        self._focus_input()

    def browse_prompt_history(self, direction: int) -> bool:
        if self.has_active_completion_popup():
            return False
        if direction not in {-1, 1}:
            return False
        composer = self.query_one("#prompt_composer", PromptComposer)
        current_text = composer.text
        if not self._prompt_history.should_handle_navigation(current_text, composer.cursor_pos):
            return False
        history_text = (
            self._prompt_history.navigate_up()
            if direction < 0
            else self._prompt_history.navigate_down()
        )
        if history_text is None:
            return False
        self._apply_history_prompt(history_text)
        return True

    def _apply_history_prompt(self, text: str) -> None:
        self._applying_history_prompt = True
        try:
            self._set_prompt_text(text)
        finally:
            self._applying_history_prompt = False
        self._focus_input()

    def _sync_prompt_history_navigation(self) -> None:
        if self._applying_history_prompt:
            return
        self._prompt_history.sync_after_edit(self._current_prompt_text())

    def _record_prompt_history(self, text: str) -> None:
        normalized = str(text or "").strip()
        if not normalized:
            return
        self._prompt_history.record_local_submission(
            normalized,
            session_id=str(getattr(self.runtime, "thread_id", None) or "").strip() or None,
        )

    def paste_prompt_from_clipboard(
        self,
        *,
        report_empty: bool,
        suppress_following_native_paste: bool = False,
    ) -> bool:
        text = self._read_clipboard_text()
        if not text:
            if report_empty:
                self._write_system_notice(self._t("system.clipboard_empty"))
            self._focus_input()
            return False
        if suppress_following_native_paste:
            self._arm_prompt_paste_suppression()
        self._insert_paste_text(text)
        self._refresh_prompt_composer()
        self._focus_input()
        return True

    def handle_paste_burst(self, text: str) -> None:
        self._clear_quit_shortcut()
        self._insert_paste_text(text)
        self._refresh_prompt_composer()

    def _insert_paste_text(self, text: str) -> None:
        appended = insert_paste_text(
            text,
            large_paste_char_threshold=self.LARGE_PASTE_CHAR_THRESHOLD,
            pending_pastes=self._pending_pastes,
            large_paste_counters=self._large_paste_counters,
            windows_drive_re=self._WINDOWS_DRIVE_RE,
            windows_unc_re=self._WINDOWS_UNC_RE,
        )
        self._append_prompt_text(appended)

    @classmethod
    def _normalize_pasted_path_text(cls, text: str) -> str:
        return normalize_pasted_path_text(
            text,
            windows_drive_re=cls._WINDOWS_DRIVE_RE,
            windows_unc_re=cls._WINDOWS_UNC_RE,
        )

    @classmethod
    def _normalize_single_pasted_path(cls, value: str) -> str | None:
        return normalize_single_pasted_path(
            value,
            windows_drive_re=cls._WINDOWS_DRIVE_RE,
            windows_unc_re=cls._WINDOWS_UNC_RE,
        )

    @staticmethod
    def _format_pasted_path(path_text: str) -> str:
        return format_pasted_path(path_text)

    @classmethod
    def _format_attachment_reference(cls, path_text: str) -> str:
        return format_attachment_reference(path_text)

    @classmethod
    def _extract_attachment_references(cls, text: str) -> tuple[str, list[PromptAttachment]]:
        return extract_attachment_references(
            text,
            windows_drive_re=cls._WINDOWS_DRIVE_RE,
            windows_unc_re=cls._WINDOWS_UNC_RE,
        )

    def _next_large_paste_placeholder(self, char_count: int) -> str:
        return next_large_paste_placeholder(char_count, counters=self._large_paste_counters)

    def _retain_pending_pastes_for_text(self, text: str) -> None:
        self._pending_pastes = retain_pending_pastes_for_text(text, self._pending_pastes)

    def _expand_pending_pastes(self, text: str) -> str:
        return expand_pending_pastes(text, self._pending_pastes)

    def _prepare_prompt_submission(self, display_text: str) -> tuple[str, list[PromptAttachment]]:
        return prepare_prompt_submission(
            display_text,
            pending_pastes=self._pending_pastes,
            windows_drive_re=self._WINDOWS_DRIVE_RE,
            windows_unc_re=self._WINDOWS_UNC_RE,
        )

    @staticmethod
    def _read_clipboard_text() -> str:
        return read_clipboard_text()

    def _arm_prompt_paste_suppression(self, text: str | None = None) -> None:
        try:
            self.query_one("#prompt_composer", PromptComposer)._arm_paste_suppression(text)
        except NoMatches:
            return

    def _focus_input(self) -> None:
        for attr_name in ("_request_user_input_overlay", "_approval_overlay", "_setup_overlay"):
            overlay = getattr(self, attr_name, None)
            if bool(getattr(overlay, "is_active", False)):
                focus = getattr(overlay, "focus", None)
                if callable(focus):
                    try:
                        focus()
                        startup_log(f"composer.focus_input.blocked active_overlay={attr_name}")
                    except Exception:
                        startup_log(
                            f"composer.focus_input.blocked_focus_failed active_overlay={attr_name}"
                        )
                return
        try:
            self.query_one("#prompt_composer", PromptComposer).focus()
            startup_log("composer.focus_input.ok")
        except NoMatches:
            startup_log("composer.focus_input.no_matches")
            return

    @staticmethod
    def _event_targets_prompt_composer(event: MouseMove | MouseUp) -> bool:
        widget = getattr(event, "widget", None)
        while widget is not None:
            if isinstance(widget, PromptComposer):
                return True
            widget = getattr(widget, "parent", None)
        return False

    def _event_targets_active_overlay(self, event: MouseMove | MouseUp) -> bool:
        widget = getattr(event, "widget", None)
        active_overlays = [
            overlay
            for overlay in (
                getattr(self, "_request_user_input_overlay", None),
                getattr(self, "_approval_overlay", None),
                getattr(self, "_setup_overlay", None),
            )
            if bool(getattr(overlay, "is_active", False))
        ]
        while widget is not None:
            if any(widget is overlay for overlay in active_overlays):
                return True
            widget = getattr(widget, "parent", None)
        return False

    def _flush_prompt_composer_burst(self) -> None:
        try:
            self.query_one("#prompt_composer", PromptComposer).flush_paste_burst()
        except NoMatches:
            return

    def _flush_prompt_composer_burst_if_due(self) -> None:
        try:
            self.query_one("#prompt_composer", PromptComposer)._flush_paste_burst_if_due()
        except NoMatches:
            return
        if self._quit_shortcut_expires_at is not None and not self._quit_shortcut_active():
            self._clear_quit_shortcut()

    def _current_prompt_text(self) -> str:
        return self.query_one("#prompt_composer", PromptComposer).text

    def _append_prompt_text(self, text: str) -> None:
        self.query_one("#prompt_composer", PromptComposer).insert_text(text)

    def _set_prompt_text(self, text: str) -> None:
        self._pending_pastes = []
        self.query_one("#prompt_composer", PromptComposer).set_text(text)

    def _clear_prompt_text(self) -> None:
        self._pending_pastes = []
        self.query_one("#prompt_composer", PromptComposer).clear_text()
