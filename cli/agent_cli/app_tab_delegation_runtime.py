from __future__ import annotations

from cli.agent_cli import app_tab_actions_runtime


class AppTabDelegationRuntimeMixin:
    def _refresh_top_title_bar(self) -> None:
        app_tab_actions_runtime.refresh_top_title_bar(self)

    def action_new_tab(self) -> None:
        app_tab_actions_runtime.action_new_tab(self)

    def action_fork_tab(self) -> None:
        app_tab_actions_runtime.action_fork_tab(self)

    def action_close_tab(self) -> None:
        app_tab_actions_runtime.action_close_tab(self)

    def action_next_tab(self) -> None:
        app_tab_actions_runtime.action_next_tab(self)

    def action_prev_tab(self) -> None:
        app_tab_actions_runtime.action_prev_tab(self)

    def _dismiss_request_user_input_overlay_for_inactive_tab(self) -> None:
        app_tab_actions_runtime.dismiss_request_user_input_overlay_for_inactive_tab(self)

    def _restore_pending_interactions_for_tab(self, tab_id: str) -> None:
        app_tab_actions_runtime.restore_pending_interactions_for_tab(self, tab_id)

    def _set_busy_for_tab(self, tab_id: str, busy: bool) -> None:
        app_tab_actions_runtime.set_busy_for_tab(self, tab_id, busy)

    def _mark_tab_transcript_updated(self, tab_id: str, *, unread: bool) -> None:
        app_tab_actions_runtime.mark_tab_transcript_updated(self, tab_id, unread=unread)

    def _capture_tab_live_turn_state(self) -> dict[str, object]:
        return app_tab_actions_runtime.capture_tab_live_turn_state(self)

    def _restore_tab_live_turn_state(self, state: dict[str, object]) -> None:
        app_tab_actions_runtime.restore_tab_live_turn_state(self, state)

    def _run_with_tab_transcript_state(self, session: object, callback) -> None:
        app_tab_actions_runtime.run_with_tab_transcript_state(self, session, callback)

    def _on_request_start_for_tab(self, tab_id: str, text: str) -> None:
        app_tab_actions_runtime.on_request_start_for_tab(self, tab_id, text)

    def _begin_activity_capture_for_tab(self, tab_id: str) -> None:
        app_tab_actions_runtime.begin_activity_capture_for_tab(self, tab_id)

    def _render_response_for_tab(self, tab_id: str, response: object) -> None:
        app_tab_actions_runtime.render_response_for_tab(self, tab_id, response)

    def _handle_response_for_tab(self, tab_id: str, response: object) -> None:
        app_tab_actions_runtime.handle_response_for_tab(self, tab_id, response)

    def _write_reply_for_tab(self, tab_id: str, text: str) -> None:
        app_tab_actions_runtime.write_reply_for_tab(self, tab_id, text)

    def _on_tab_activity(self, tab_id: str, event: object) -> None:
        app_tab_actions_runtime.on_tab_activity(self, tab_id, event)

    def _on_tab_turn_event(self, tab_id: str, event: object) -> None:
        app_tab_actions_runtime.on_tab_turn_event(self, tab_id, event)

    def _echo_prompt_for_tab(
        self,
        tab_id: str,
        text: str,
        attachments: list | None = None,
    ) -> None:
        app_tab_actions_runtime.echo_prompt_for_tab(self, tab_id, text, attachments)

    def _on_idle_for_tab(self, tab_id: str) -> None:
        app_tab_actions_runtime.on_idle_for_tab(self, tab_id)


__all__ = ["AppTabDelegationRuntimeMixin"]
