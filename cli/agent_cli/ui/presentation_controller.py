from __future__ import annotations

from time import monotonic

from textual.color import Color
from textual.css.query import NoMatches
from textual.widgets import Static

from cli.agent_cli.startup_debug import startup_log
from cli.agent_cli.ui import bottom_dock_decision_runtime as bottom_dock_decision_runtime_service
from cli.agent_cli.ui import bottom_dock_layout_runtime as bottom_dock_layout_runtime_service
from cli.agent_cli.ui import bottom_dock_render_runtime as bottom_dock_render_runtime_service
from cli.agent_cli.ui import context_window_status_runtime, status_controller_runtime
from cli.agent_cli.ui.composer import PromptComposer
from cli.agent_cli.ui.presentation import PresentationSettings
from cli.agent_cli.ui.status_indicator import IdleCatAnimator, build_idle_status_text
from cli.agent_cli.ui.theme import build_app_css
from cli.agent_cli.ui.theme_runtime import scrollbar_palette
from cli.agent_cli.ui.transcript_virtual_list import TranscriptVirtualList
from cli.agent_cli.ui.widgets import SlashCommandPopup, TranscriptArea


class PresentationControllerMixin:
    def _prompt_has_text(self) -> bool:
        try:
            return bool(str(self.query_one("#prompt_composer", PromptComposer).text or "").strip())
        except NoMatches:
            return False

    def _apply_presentation(self, presentation: PresentationSettings) -> None:
        self._presentation = presentation
        self._theme = presentation.theme
        self._messages = presentation.messages
        try:
            self.runtime.presentation_locale = presentation.locale
        except Exception:
            pass
        self.CSS = build_app_css(self._theme)
        self.title = self._messages.text("app.title")
        self.sub_title = self._subtitle_text(self._busy)
        try:
            self.refresh_css(animate=False)
        except Exception:
            pass
        self._apply_presentation_to_widgets()
        try:
            self._sync_transcript()
        except NoMatches:
            pass
        try:
            self._update_bottom_dock(max(1, self.size.width))
            self._update_completion_popup()
            self._refresh_prompt_composer()
        except NoMatches:
            pass

    def _apply_presentation_to_widgets(self) -> None:
        try:
            self.screen.styles.background = Color.parse(self._theme.app_bg)
            self.screen.styles.color = Color.parse(self._theme.text_secondary)
        except Exception:
            pass
        try:
            self.query_one("#prompt_composer", PromptComposer).set_presentation(
                presentation=self._presentation
            )
        except NoMatches:
            pass
        try:
            self.query_one("#slash_popup", SlashCommandPopup).set_presentation(
                presentation=self._presentation
            )
        except NoMatches:
            pass
        try:
            from cli.agent_cli.ui.setup_modal import SetupOverlay

            self.query_one(f"#{SetupOverlay.ROOT_ID}", SetupOverlay).set_presentation(
                self._presentation
            )
        except NoMatches:
            pass
        scrollbar = scrollbar_palette(self._theme)
        try:
            main_log = self.query_one("#main_log", TranscriptArea)
            main_log.styles.background = Color.parse(self._theme.panel_bg)
            main_log.styles.scrollbar_background = Color.parse(scrollbar["track"])
            main_log.styles.scrollbar_background_hover = Color.parse(scrollbar["track_hover"])
            main_log.styles.scrollbar_background_active = Color.parse(scrollbar["track_active"])
            main_log.styles.scrollbar_color = Color.parse(scrollbar["thumb"])
            main_log.styles.scrollbar_color_hover = Color.parse(scrollbar["thumb_hover"])
            main_log.styles.scrollbar_color_active = Color.parse(scrollbar["thumb_active"])
            main_log.styles.scrollbar_corner_color = Color.parse(scrollbar["corner"])
            main_log.refresh(repaint=True, layout=False)
        except NoMatches:
            pass
        try:
            transcript_log = self.query_one("#transcript_log", TranscriptVirtualList)
            transcript_log.styles.background = Color.parse(self._theme.panel_bg)
            transcript_log.styles.scrollbar_background = Color.parse(scrollbar["track"])
            transcript_log.styles.scrollbar_background_hover = Color.parse(scrollbar["track_hover"])
            transcript_log.styles.scrollbar_background_active = Color.parse(
                scrollbar["track_active"]
            )
            transcript_log.styles.scrollbar_color = Color.parse(scrollbar["thumb"])
            transcript_log.styles.scrollbar_color_hover = Color.parse(scrollbar["thumb_hover"])
            transcript_log.styles.scrollbar_color_active = Color.parse(scrollbar["thumb_active"])
            transcript_log.styles.scrollbar_corner_color = Color.parse(scrollbar["corner"])
            transcript_log.refresh(repaint=True, layout=False)
        except NoMatches:
            pass
        try:
            transcript_hint = self.query_one("#transcript_task_hint", Static)
            transcript_hint.styles.height = 1
            transcript_hint.styles.padding = (0, 1)
            transcript_hint.styles.background = Color.parse(self._theme.info_surface_bg)
            transcript_hint.styles.color = Color.parse(self._theme.text_secondary)
            transcript_hint.styles.text_align = "center"
            transcript_hint.refresh(repaint=True, layout=False)
        except NoMatches:
            pass
        for widget_id, background, color in (
            ("#top_title_row", self._theme.info_surface_bg, None),
            ("#top_title_icon", self._theme.info_surface_bg, self._theme.text_secondary),
            ("#top_title_bar", self._theme.info_surface_bg, self._theme.text_secondary),
            ("#work_area", self._theme.app_bg, None),
            ("#tab_bar", self._theme.info_surface_bg, self._theme.text_secondary),
            ("#bottom_dock", self._theme.app_bg, None),
            ("#slash_popup", self._theme.overlay_bg, self._theme.text_secondary),
            ("#status_line", self._theme.info_surface_bg, self._theme.text_dim),
            ("#composer_shell", self._theme.user_surface_bg, None),
            ("#composer_footer", self._theme.info_surface_bg, self._theme.text_dim),
            ("#prompt_composer", self._theme.user_surface_bg, self._theme.text_primary),
        ):
            try:
                widget = self.query_one(widget_id)
                widget.styles.background = Color.parse(background)
                if color:
                    widget.styles.color = Color.parse(color)
                widget.refresh(repaint=True, layout=False)
            except NoMatches:
                continue
        for widget_id in (
            "#top_title_row",
            "#top_title_icon",
            "#top_title_bar",
            "#work_area",
            "#tab_bar",
            "#status_line",
            "#composer_footer",
            "#composer_shell",
            "#bottom_dock",
            "#body",
        ):
            try:
                self.query_one(widget_id).refresh(repaint=True, layout=False)
            except NoMatches:
                continue
        self._apply_screen_state_to_widgets()

    def _apply_screen_state_to_widgets(self) -> None:
        screen_mode = str(getattr(self, "_screen_mode", "prompt") or "prompt").strip().lower()
        is_transcript = screen_mode == "transcript"
        try:
            transcript_log = self.query_one("#transcript_log", TranscriptVirtualList)
            transcript_log.styles.display = "block" if is_transcript else "none"
            transcript_log.refresh(repaint=True, layout=True)
        except NoMatches:
            pass
        try:
            transcript_hint = self.query_one("#transcript_task_hint", Static)
            refresh_hint = getattr(self, "_refresh_transcript_task_hint", None)
            if callable(refresh_hint):
                refresh_hint()
            transcript_hint.styles.display = "block" if is_transcript else "none"
            transcript_hint.refresh(repaint=True, layout=True)
        except NoMatches:
            pass
        try:
            main_log = self.query_one("#main_log", TranscriptArea)
            main_log.styles.display = "none" if is_transcript else "block"
            main_log.refresh(repaint=True, layout=True)
        except NoMatches:
            pass
        try:
            composer_shell = self.query_one("#composer_shell")
            composer_shell.styles.display = "none" if is_transcript else "block"
            composer_shell.refresh(repaint=True, layout=True)
        except NoMatches:
            pass
        try:
            prompt = self.query_one("#prompt_composer", PromptComposer)
            prompt.styles.display = "none" if is_transcript else "block"
            prompt.refresh(repaint=True, layout=True)
        except NoMatches:
            pass
        if is_transcript:
            try:
                self.query_one("#slash_popup", SlashCommandPopup).styles.display = "none"
            except NoMatches:
                pass

    def _update_bottom_dock(self, width: int) -> None:
        content_width = max(1, int(width))
        render_state = self._build_bottom_dock_render_state(content_width)
        self.query_one("#status_line", Static).update(render_state.primary_line)
        self.query_one("#composer_footer", Static).update(render_state.secondary_line)
        try:
            self.query_one("#prompt_composer", PromptComposer).refresh(repaint=True, layout=False)
        except NoMatches:
            pass

    def _build_status_indicator_line(self, width: int):
        if self._quit_shortcut_active():
            self._idle_status_started_at = None
            return self._crop_one_line(f"• {self._t('status.quit_confirm')}", width)
        if self._busy:
            self._idle_status_started_at = None
            if self._assistant_message_streaming_active or self._busy_status_hidden:
                return ""
            return self._build_busy_hint(width)
        pending_approvals = self._pending_approval_count()
        approval_policy = str(self.status_data.get("approval_policy", "") or "").strip().lower()
        if pending_approvals > 0 and approval_policy != "never":
            self._idle_status_started_at = None
            return self._build_pending_approval_hint(width, pending_approvals)
        tab_pending_hint = self._build_tab_pending_interaction_hint(width)
        if tab_pending_hint:
            self._idle_status_started_at = None
            return tab_pending_hint
        # Keep the primary status line as a transient running/waiting surface.
        # Completed task summaries stay in transcript/history instead of lingering
        # in the bottom status bar after the turn has finished.
        if self._prompt_has_text():
            return ""
        if not self._presentation.idle_cat_enabled:
            self._idle_status_started_at = None
            return ""
        current_time = monotonic()
        if self._idle_status_started_at is None:
            self._idle_status_started_at = current_time
            self._idle_cat_animator = IdleCatAnimator()
        if current_time - self._idle_status_started_at < self.IDLE_STATUS_DELAY_SECONDS:
            return ""
        return build_idle_status_text(
            width=width, animator=self._idle_cat_animator, theme=self._theme
        )

    def _context_window_footer_text(self) -> str:
        return context_window_status_runtime.context_window_footer_text(
            status_data=self.status_data,
            translate_fn=self._t,
        )

    def _build_bottom_dock_render_state(
        self, width: int
    ) -> bottom_dock_render_runtime_service.BottomDockRenderState:
        prompt_has_text = self._prompt_has_text()
        shortcut_overlay_active = bool(getattr(self, "_shortcut_overlay_active", False))
        if (
            shortcut_overlay_active
            and not prompt_has_text
            and str(getattr(self, "_screen_mode", "prompt") or "prompt").strip().lower() == "prompt"
        ):
            return bottom_dock_render_runtime_service.BottomDockRenderState(
                primary_line=self._crop_one_line(
                    f"• {self._t('footer.shortcuts_overlay_line1')}",
                    width,
                ),
                secondary_line=self._crop_one_line(
                    f"  {self._t('footer.shortcuts_overlay_line2')}",
                    width,
                ),
            )
        queue_actionable = bool(self._busy and prompt_has_text)
        queue_prompt_actionable = getattr(self, "_queue_prompt_actionable", None)
        if callable(queue_prompt_actionable):
            try:
                queue_actionable = bool(queue_prompt_actionable())
            except Exception:
                queue_actionable = bool(self._busy and prompt_has_text)
        queue_dominant_active = bool(queue_actionable and not self._quit_shortcut_active())
        status_line = self._build_status_indicator_line(width)
        passive_summary_active = bool(
            status_line
        ) and status_line == self._build_passive_status_summary(width)
        pending_approval_footer = ""
        pending_approvals = self._pending_approval_count()
        approval_policy = str(self.status_data.get("approval_policy", "") or "").strip().lower()
        if pending_approvals > 0 and approval_policy != "never":
            pending_approval_footer = self._build_pending_approval_footer_hint(width)

        decision = bottom_dock_decision_runtime_service.decide_bottom_dock_content(
            screen_mode=str(getattr(self, "_screen_mode", "prompt") or "prompt"),
            status_line=status_line,
            passive_summary_active=passive_summary_active,
            prompt_has_text=prompt_has_text,
            busy=bool(self._busy),
            queue_dominant_active=queue_dominant_active,
            footer_context_text=self._context_window_footer_text(),
            footer_shortcuts_text=f"  {self._t('footer.shortcuts')}",
            footer_queue_text=f"  {self._t('footer.queue_message')}",
            transcript_prompt_view_text=f"  {self._t('footer.transcript_prompt_view')}",
            transcript_exit_text=self._t("footer.transcript_exit"),
        )

        footer_left = decision.footer_left
        if pending_approval_footer:
            footer_left = pending_approval_footer
        if (
            not footer_left
            and str(getattr(self, "_screen_mode", "prompt") or "prompt").strip().lower()
            != "transcript"
        ):
            footer_left = status_controller_runtime.build_provider_summary_text(
                status_data=self.status_data,
                cwd=str(
                    getattr(self.runtime, "cwd", "") or getattr(self, "_workspace_root", "") or ""
                ),
            )

        footer_line = bottom_dock_layout_runtime_service.compose_left_right_line(
            left=footer_left,
            right=decision.footer_right,
            width=width,
            crop_one_line_fn=self._crop_one_line,
        )
        return bottom_dock_render_runtime_service.BottomDockRenderState(
            primary_line=decision.status_line,
            secondary_line=footer_line,
        )

    def _build_bottom_dock_lines(self, width: int) -> tuple[str, str]:
        render_state = self._build_bottom_dock_render_state(width)
        return render_state.primary_line, render_state.secondary_line

    def _build_footer_line(self, width: int) -> str:
        return self._build_bottom_dock_render_state(width).secondary_line

    def _apply_layout_state(self, width: int) -> None:
        try:
            self._apply_screen_state_to_widgets()
            self._update_status({})
            self._refresh_prompt_composer()
            self._refresh_transcript_rendering()
            self._update_tab_bar_compact(width)
        except NoMatches:
            return
        self._refresh_top_title_bar()

    def _update_tab_bar_compact(self, width: int) -> None:
        try:
            from cli.agent_cli.ui.tab_bar import TabBar

            tab_bar = self.query_one("#tab_bar", TabBar)
        except NoMatches:
            return
        tab_bar.update_compact(width)
        compact = tab_bar.is_compact
        scrollbar_width = 1 if compact else 2
        for widget_id in ("#main_log", "#transcript_log"):
            try:
                widget = self.query_one(widget_id)
                widget.styles.scrollbar_size_vertical = scrollbar_width
            except NoMatches:
                continue

    def _stabilize_initial_frame(self) -> None:
        startup_log("presentation.stabilize_initial_frame.begin")
        self._apply_layout_state(max(1, self.size.width))
        try:
            self.query_one("#main_log", TranscriptArea).refresh(repaint=True, layout=True)
            self.query_one("#transcript_log", TranscriptVirtualList).refresh(
                repaint=True, layout=True
            )
            self.query_one("#bottom_dock").refresh(repaint=True, layout=True)
            self.refresh(repaint=True, layout=True)
            self._focus_input()
            startup_log("presentation.stabilize_initial_frame.end")
        except NoMatches:
            startup_log("presentation.stabilize_initial_frame.no_matches")
            return
