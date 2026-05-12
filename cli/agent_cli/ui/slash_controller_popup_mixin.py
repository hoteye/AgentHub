from __future__ import annotations

from cli.agent_cli.ui import slash_controller_popup_runtime
from cli.agent_cli.ui.widgets import SlashCommandPopup


class SlashControllerPopupMixin:
    def has_active_slash_popup(self) -> bool:
        return bool(self._slash_matches)

    def has_active_file_popup(self) -> bool:
        return bool(self._file_matches)

    def has_active_completion_popup(self) -> bool:
        return self.has_active_file_popup() or self.has_active_slash_popup()

    def dismiss_slash_popup(self) -> bool:
        if not self.has_active_completion_popup():
            return False
        self._slash_matches, self._slash_selected_index, self._slash_popup_mode = [], 0, "slash"
        self._file_matches, self._file_selected_index = [], 0
        popup = self.query_one("#slash_popup", SlashCommandPopup)
        popup.set_items([], 0, "")
        popup.styles.display = "none"
        self._refresh_prompt_composer()
        return True

    def move_slash_selection(self, offset: int) -> bool:
        target, next_index = slash_controller_popup_runtime.moved_popup_selection(
            has_file_popup=self.has_active_file_popup(),
            file_selected_index=self._file_selected_index,
            file_matches=self._file_matches,
            slash_selected_index=self._slash_selected_index,
            slash_matches=self._slash_matches,
            offset=offset,
        )
        if target == "file":
            self._file_selected_index = next_index
            popup = self.query_one("#slash_popup", SlashCommandPopup)
            popup.set_items(
                self._file_matches, self._file_selected_index, self._file_query() or "", mode="file"
            )
            return True
        if target != "slash":
            return False
        self._slash_selected_index = next_index
        popup = self.query_one("#slash_popup", SlashCommandPopup)
        popup.set_items(
            self._slash_matches,
            self._slash_selected_index,
            self._slash_query() or "",
            mode=self._slash_popup_mode,
        )
        return True

    def _apply_slash_popup_state(
        self, popup: SlashCommandPopup, state: slash_controller_popup_runtime.PopupState
    ) -> None:
        self._slash_matches, self._slash_selected_index = state.matches, state.selected_index
        self._slash_popup_mode = state.mode
        self._render_popup_state(popup, state)

    def _apply_file_popup_state(
        self, popup: SlashCommandPopup, state: slash_controller_popup_runtime.PopupState
    ) -> None:
        self._file_matches = state.matches
        self._file_selected_index = state.selected_index
        self._render_popup_state(popup, state)

    @staticmethod
    def _render_popup_state(
        popup: SlashCommandPopup, state: slash_controller_popup_runtime.PopupState
    ) -> None:
        if not state.visible:
            popup.set_items([], 0, "")
            popup.styles.display = "none"
            return
        popup.set_items(state.matches, state.selected_index, state.query, mode=state.mode)
        popup.styles.height = popup.visible_line_count()
        popup.styles.display = "block"

    def _slash_popup_command_name(self, selected: dict[str, str] | None = None) -> str:
        if self._slash_popup_mode == "slash_arg":
            context = self._slash_completion_context()
            if context is not None:
                command_name = str(context.command_name or "").strip()
                if command_name:
                    return command_name
        if selected is None and 0 <= self._slash_selected_index < len(self._slash_matches):
            selected = self._slash_matches[self._slash_selected_index]
        if selected is None:
            return ""
        command_name = str(selected.get("name") or "").strip()
        if command_name:
            if self._slash_popup_mode == "slash_arg" and ":" in command_name:
                return command_name.split(":", 1)[0].strip()
            return command_name
        usage = str(selected.get("usage") or "").strip()
        if usage.startswith("/"):
            return usage[1:].split(" ", 1)[0].strip()
        return ""

    def _slash_popup_command_available_during_busy(
        self, selected: dict[str, str] | None = None
    ) -> bool:
        return self._slash_command_available_during_busy(
            self._slash_popup_busy_policy_subject(selected)
        )

    def _slash_popup_busy_policy_subject(self, selected: dict[str, str] | None = None) -> str:
        if selected is None and 0 <= self._slash_selected_index < len(self._slash_matches):
            selected = self._slash_matches[self._slash_selected_index]
        selected_item = selected or {}
        insert_text = str(selected_item.get("insert_text") or "").strip()
        if insert_text.startswith("/"):
            return insert_text
        if self._slash_popup_mode == "slash_arg":
            current_text = str(self._current_prompt_text() or "").strip()
            if current_text.startswith("/"):
                return current_text
        command_name = self._slash_popup_command_name(selected_item)
        if command_name:
            return f"/{command_name}"
        return insert_text

    def _busy_slash_policy_allows(self, text_or_name: str, *, notify: bool) -> bool:
        slash_commands_blocked = (
            bool(self._slash_commands_blocked_by_pending_runtime_work())
            if callable(getattr(self, "_slash_commands_blocked_by_pending_runtime_work", None))
            else self._has_pending_runtime_work()
        )
        if not slash_commands_blocked:
            return True
        allowed = self._slash_command_available_during_busy(text_or_name)
        if not allowed and notify:
            self._write_system_notice(self._BUSY_SLASH_COMMAND_NOTICE)
            self._focus_input()
        return allowed

    def complete_slash_popup(self) -> bool:
        if self.has_active_file_popup():
            return self._insert_selected_file_reference()
        if self.has_active_slash_popup() and self._slash_popup_mode == "slash_arg":
            selected = (
                self._slash_matches[self._slash_selected_index] if self._slash_matches else None
            )
            if selected is None:
                return False
            if not self._busy_slash_policy_allows(
                self._slash_popup_busy_policy_subject(selected),
                notify=True,
            ):
                return True
            return self._apply_slash_completion_item(selected or {})
        query = self._slash_query()
        if query is None:
            return False
        completion = self.runtime.slash_command_completion(query)
        if not completion:
            completion = self._complete_local_slash_command(query)
        if not completion:
            return False
        if not self._busy_slash_policy_allows(completion, notify=True):
            return True
        self._set_prompt_text(completion)
        self._focus_input()
        return True

    def handle_composer_enter(self) -> bool:
        if self.has_active_file_popup():
            return self._insert_selected_file_reference()
        if not self.has_active_slash_popup():
            return False
        selected = self._slash_matches[self._slash_selected_index] if self._slash_matches else None
        if selected is None:
            return False
        if not self._busy_slash_policy_allows(
            self._slash_popup_busy_policy_subject(selected),
            notify=True,
        ):
            return True
        if self._slash_popup_mode == "slash_arg":
            current_text = self._current_prompt_text().rstrip()
            selected_insert_text = str(selected.get("insert_text") or "").rstrip()
            submit_after_apply = str(selected.get("submit_after_apply") or "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            if submit_after_apply and selected_insert_text.startswith("/"):
                self._set_prompt_text(selected_insert_text)
                self.call_next(self.action_submit_prompt)
                return True
            if selected_insert_text and selected_insert_text != current_text:
                return self._apply_slash_completion_item(selected)
            return False
        self._set_prompt_text(
            str(selected.get("usage") or f"/{selected.get('name') or ''}").split(" ", 1)[0]
        )
        self.call_next(self.action_submit_prompt)
        return True
