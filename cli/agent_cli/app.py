from __future__ import annotations

import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.events import MouseDown, MouseMove, MouseUp, Resize
from textual.widgets import Static

from cli.agent_cli import (
    app_bindings_runtime,
    app_bootstrap_helpers_runtime,
    app_event_helpers,
    app_preview_actions_runtime,
    app_projection_helpers_runtime,
    app_property_proxy_runtime,
    app_pure_helpers_runtime,
    app_runtime_support_runtime,
    app_shutdown_runtime,
)
from cli.agent_cli import (
    app_tab_actions_runtime as app_tab_actions_runtime,
)
from cli.agent_cli.app_runtime_flow import (
    AppRuntimeFlowMixin,
)
from cli.agent_cli.app_runtime_flow import (
    _PendingRequestUserInput as _PendingRequestUserInputRuntime,
)
from cli.agent_cli.app_tab_delegation_runtime import AppTabDelegationRuntimeMixin
from cli.agent_cli.startup_debug import startup_log, startup_timer
from cli.agent_cli.ui import (
    PromptComposer,
    SlashCommandPopup,
    TranscriptArea,
    TranscriptVirtualList,
    resolve_runtime,
    top_title_summary_runtime,
    write_clipboard_text,
)
from cli.agent_cli.ui.app_transcript_coordination import AppTranscriptCoordinationMixin
from cli.agent_cli.ui.composer_controller import ComposerControllerMixin
from cli.agent_cli.ui.live_turn_controller import LiveTurnControllerMixin
from cli.agent_cli.ui.presentation_controller import PresentationControllerMixin
from cli.agent_cli.ui.prompt_transcript_window_runtime import PromptTranscriptWindowState
from cli.agent_cli.ui.slash_controller import SlashControllerMixin
from cli.agent_cli.ui.status_controller import StatusControllerMixin
from cli.agent_cli.ui.tab_bar import TabBar
from cli.agent_cli.ui.transcript_controller import TranscriptControllerMixin

if TYPE_CHECKING:
    from cli.agent_cli.runtime import AgentCliRuntime


_PendingRequestUserInput = _PendingRequestUserInputRuntime


class AgentCliApp(
    AppRuntimeFlowMixin,
    StatusControllerMixin,
    PresentationControllerMixin,
    ComposerControllerMixin,
    TranscriptControllerMixin,
    LiveTurnControllerMixin,
    SlashControllerMixin,
    AppTranscriptCoordinationMixin,
    AppTabDelegationRuntimeMixin,
    App,
):
    AUTO_FOCUS = "#prompt_composer"
    LARGE_PASTE_CHAR_THRESHOLD = app_bindings_runtime.LARGE_PASTE_CHAR_THRESHOLD
    MAX_USER_INPUT_TEXT_CHARS = app_bindings_runtime.MAX_USER_INPUT_TEXT_CHARS
    QUIT_SHORTCUT_TIMEOUT_SECONDS = app_bindings_runtime.QUIT_SHORTCUT_TIMEOUT_SECONDS
    IDLE_STATUS_DELAY_SECONDS = app_bindings_runtime.IDLE_STATUS_DELAY_SECONDS
    FILE_POPUP_MATCH_LIMIT = app_bindings_runtime.FILE_POPUP_MATCH_LIMIT
    COMMAND_OUTPUT_MAX_LINES = app_bindings_runtime.COMMAND_OUTPUT_MAX_LINES
    _QUEUED_REQUEST_BUSY_LABEL_KEYS = dict(app_bindings_runtime.QUEUED_REQUEST_BUSY_LABEL_KEYS)
    CSS = app_bindings_runtime.APP_CSS
    TITLE = app_bindings_runtime.APP_TITLE
    SUB_TITLE = app_bindings_runtime.APP_SUB_TITLE
    BINDINGS = list(app_bindings_runtime.APP_BINDINGS)
    _WINDOWS_DRIVE_RE = app_bindings_runtime.WINDOWS_DRIVE_RE
    _WINDOWS_UNC_RE = app_bindings_runtime.WINDOWS_UNC_RE
    _DEFAULT_THREAD_NAME_RE = app_bindings_runtime.DEFAULT_THREAD_NAME_RE

    def __init__(
        self,
        *,
        runtime: AgentCliRuntime | None = None,
        prompt_history_home: Path | None = None,
        language: str | None = None,
        theme_id: str | None = None,
    ) -> None:
        with startup_timer("app.init.resolve_runtime"):
            resolved_runtime = resolve_runtime(runtime)
        with startup_timer("app.init.bootstrap_context"):
            bootstrap = app_bootstrap_helpers_runtime.build_bootstrap_context(
                runtime=resolved_runtime,
                language=language,
                theme_id=theme_id,
            )
        app_bootstrap_helpers_runtime.apply_pre_super_state(
            self,
            language=language,
            theme_id=theme_id,
            context=bootstrap,
        )
        with startup_timer("app.init.textual_super"):
            super().__init__(driver_class=bootstrap.driver_class)
        app_bootstrap_helpers_runtime.initialize_app_state(
            self,
            prompt_history_home=prompt_history_home,
            context=bootstrap,
        )

    def exit(self, *args: object, **kwargs: object) -> None:
        startup_log(
            "app.exit.called "
            f"exit_requested={getattr(self, '_exit_requested', False)} "
            f"shutdown={getattr(self, '_shutdown_initiated', False)}"
        )
        return super().exit(*args, **kwargs)

    def _handle_exception(self, error: Exception) -> None:
        startup_log(f"app.handle_exception {error.__class__.__name__}: {error!r}")
        startup_log(traceback.format_exc().rstrip())
        return super()._handle_exception(error)

    @property
    def runtime(self) -> AgentCliRuntime:
        return app_property_proxy_runtime.get_runtime(self)

    @runtime.setter
    def runtime(self, value: AgentCliRuntime) -> None:
        app_property_proxy_runtime.set_runtime(self, value)

    @property
    def status_data(self) -> dict:
        return app_property_proxy_runtime.get_status_data(self)

    @status_data.setter
    def status_data(self, value: dict) -> None:
        app_property_proxy_runtime.set_status_data(self, value)

    @property
    def _request_queue(self):
        return app_property_proxy_runtime.get_request_queue(self)

    @_request_queue.setter
    def _request_queue(self, value) -> None:
        app_property_proxy_runtime.set_request_queue(self, value)

    @property
    def _request_worker_task(self):
        return app_property_proxy_runtime.get_request_worker_task(self)

    @_request_worker_task.setter
    def _request_worker_task(self, value) -> None:
        app_property_proxy_runtime.set_request_worker_task(self, value)

    def _t(self, key: str, **kwargs: object) -> str:
        return self._messages.text(key, **kwargs)

    def copy_to_clipboard(self, text: str) -> None:
        if write_clipboard_text(text):
            return
        super().copy_to_clipboard(text)

    def _subtitle_text(self, busy: bool) -> str:
        return app_runtime_support_runtime.subtitle_text(self._t, busy=busy)

    def _resolve_transcript_task_hint_text(self) -> str:
        return app_projection_helpers_runtime.resolve_transcript_task_hint_text(
            runtime=self.runtime,
            top_title_text=self._top_title_text,
            base_title=self._top_title_base,
        )

    def _refresh_transcript_task_hint(self) -> None:
        self._transcript_task_hint_text = self._resolve_transcript_task_hint_text()
        try:
            task_hint = self.query_one("#transcript_task_hint", Static)
        except NoMatches:
            return
        measured_width = int(getattr(task_hint.size, "width", 0) or 0)
        if measured_width <= 0:
            measured_width = max(1, int(self.size.width))
        task_hint.update(self._crop_one_line(self._transcript_task_hint_text, measured_width))

    def _set_top_title_base(self) -> None:
        self._top_title_text = self._top_title_base
        self._refresh_top_title_bar()

    def _normalize_thread_title_candidate(self, value: str) -> str:
        return app_pure_helpers_runtime.normalize_thread_title_candidate(
            value,
            default_thread_name_re=self._DEFAULT_THREAD_NAME_RE,
        )

    def _resolve_thread_title_from_runtime(self, *, refresh_from_store: bool) -> str:
        return app_projection_helpers_runtime.resolve_thread_title_from_runtime(
            runtime=self.runtime,
            refresh_from_store=refresh_from_store,
            default_thread_name_re=self._DEFAULT_THREAD_NAME_RE,
        )

    def _sync_top_title_from_thread_name(self, *, refresh_from_store: bool) -> bool:
        thread_title = self._resolve_thread_title_from_runtime(
            refresh_from_store=refresh_from_store
        )
        if not thread_title:
            return False
        self._top_title_text = thread_title
        self._refresh_top_title_bar()
        return True

    def _set_top_title_from_prompt(self, prompt: str) -> None:
        if self._sync_top_title_from_thread_name(refresh_from_store=False):
            return
        if not top_title_summary_runtime.should_update_title_from_prompt(prompt):
            return
        content_width = max(1, int(self.size.width) - 2)
        self._top_title_text = app_projection_helpers_runtime.top_title_text_from_prompt(
            prompt=prompt,
            base_title=self._top_title_base,
            width=content_width,
            crop_one_line_fn=self._crop_one_line,
        )
        self._refresh_top_title_bar()

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            with Vertical(id="work_area"):
                with Horizontal(id="top_title_row"):
                    yield Static(self._top_title_leading_symbol, id="top_title_icon")
                    yield Static(self._top_title_text, id="top_title_bar")
                    yield Static(">>", id="split_toggle_btn")
                yield Static(self._transcript_task_hint_text, id="transcript_task_hint")
                with Horizontal(id="content_area"):
                    yield TabBar(id="tab_bar", orientation="vertical")
                    yield TranscriptArea(
                        "\n".join(self._transcript_lines),
                        id="main_log",
                        read_only=True,
                        soft_wrap=True,
                        show_line_numbers=False,
                    )
                    yield TranscriptVirtualList(id="transcript_log")
                with Vertical(id="bottom_dock"):
                    yield SlashCommandPopup(id="slash_popup", presentation=self._presentation)
                    yield Static("", id="status_line")
                    with Container(id="composer_shell"):
                        yield PromptComposer(
                            "",
                            id="prompt_composer",
                            presentation=self._presentation,
                        )
                    yield Static("", id="composer_footer")

    def on_mount(self) -> None:
        app_event_helpers.on_mount(self)

    def on_resize(self, event: Resize) -> None:
        self._apply_layout_state(event.size.width)

    def on_key(self, event) -> None:
        app_event_helpers.on_key(self, event)

    def on_mouse_down(self, event: MouseDown) -> None:
        app_event_helpers.on_mouse_down(self, event)

    def on_mouse_up(self, event: MouseUp) -> None:
        app_event_helpers.on_mouse_up(self, event)

    def on_mouse_move(self, event: MouseMove) -> None:
        app_event_helpers.on_mouse_move(self, event)

    def _record_idle_mouse_position(self, event: MouseMove | MouseUp) -> None:
        app_event_helpers.record_idle_mouse_position(self, event)

    async def on_unmount(self) -> None:
        await app_shutdown_runtime.on_unmount(self)

    async def action_refresh_state(self) -> None:
        if not self._busy_shortcut_policy_allows("/provider"):
            return
        notice_key = app_runtime_support_runtime.notice_key_for_pending(
            has_pending_work=self._has_pending_runtime_work(),
            queued_key="system.queued_provider",
            running_key="system.running_provider",
        )
        self._write_system_notice(self._t(notice_key))
        await self._enqueue_runtime_request("/provider", [], priority="later")

    async def action_show_tools(self) -> None:
        if not self._busy_shortcut_policy_allows("/tools"):
            return
        notice_key = app_runtime_support_runtime.notice_key_for_pending(
            has_pending_work=self._has_pending_runtime_work(),
            queued_key="system.queued_tools",
            running_key="system.running_tools",
        )
        self._write_system_notice(self._t(notice_key))
        await self._enqueue_runtime_request("/tools", [], priority="later")

    def _busy_shortcut_policy_allows(self, command_text: str) -> bool:
        if not self._has_pending_runtime_work():
            return True
        if self._slash_command_available_during_busy(command_text):
            return True
        self._write_system_notice(self._BUSY_SLASH_COMMAND_NOTICE)
        self._focus_input()
        return False

    def action_ctrl_c(self) -> None:
        app_event_helpers.action_ctrl_c(self)

    def action_focused_undo_or_noop(self) -> None:
        composer = self._focused_prompt_composer()
        if composer is None:
            return
        composer.undo()

    def action_clear_logs(self) -> None:
        self._clear_quit_shortcut()
        self._transcript_lines = []
        self._transcript_screen_snapshot_entries = None
        self._prompt_transcript_window_state = PromptTranscriptWindowState()
        last_entry = self._transcript_entries[-1] if self._transcript_entries else None
        self._prompt_transcript_clear_boundary_entry_id = (
            str(last_entry.entry_id or "").strip() or None
        )
        try:
            self.query_one("#main_log", TranscriptArea).load_transcript([])
        except NoMatches:
            pass
        self._write_system_notice(self._t("system.log_cleared"))
        self._focus_input()

    def action_toggle_transcript(self) -> None:
        target_mode = "transcript" if self._screen_mode != "transcript" else "prompt"
        self._set_screen_mode(target_mode)

    def action_interrupt_run(self) -> None:
        app_event_helpers.action_interrupt_run(self)

    def _focused_prompt_composer(self) -> PromptComposer | None:
        focused = getattr(self, "focused", None)
        if isinstance(focused, PromptComposer):
            return focused
        try:
            composer = self.query_one("#prompt_composer", PromptComposer)
        except NoMatches:
            return None
        if composer.has_focus:
            return composer
        return None

    def handle_escape_interrupt(self) -> bool:
        if not self._has_interruptible_run():
            return False
        self.action_interrupt_run()
        return True

    def handle_escape_key(self) -> bool:
        return app_event_helpers.handle_escape_key(self)

    def on_prompt_composer_changed(self) -> None:
        app_event_helpers.on_prompt_composer_changed(self)

    def _user_input_too_large_message(self, actual_chars: int) -> str:
        return self._t(
            "system.message_too_large",
            limit=self.MAX_USER_INPUT_TEXT_CHARS,
            actual=actual_chars,
        )

    def _clear_shortcut_overlay(self) -> None:
        if not self._shortcut_overlay_active:
            return
        self._shortcut_overlay_active = False
        try:
            self._update_bottom_dock(max(1, self.size.width))
        except NoMatches:
            return

    def toggle_shortcut_overlay_from_question_mark(self) -> bool:
        if not app_pure_helpers_runtime.can_toggle_shortcut_overlay(
            screen_mode=getattr(self, "_screen_mode", "prompt"),
            prompt_text=self._current_prompt_text(),
        ):
            return False
        self._shortcut_overlay_active = not self._shortcut_overlay_active
        try:
            self._update_bottom_dock(max(1, self.size.width))
        except NoMatches:
            pass
        return True

    def action_toggle_latest_web_item(self) -> None:
        app_preview_actions_runtime.action_toggle_latest_web_item(self)
