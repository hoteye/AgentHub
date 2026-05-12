from __future__ import annotations

from cli.agent_cli.ui import slash_controller_helpers as slash_helpers
from cli.agent_cli.ui.composer import PromptComposer
from cli.agent_cli.ui.presentation import PresentationSettings, save_user_presentation_preferences
from cli.agent_cli.ui.slash_controller_helpers import SlashCompletionContext
from cli.agent_cli.ui.slash_controller_popup_mixin import SlashControllerPopupMixin


class SlashControllerMixin(SlashControllerPopupMixin):
    @staticmethod
    def _local_slash_command_specs(locale: str | None = None) -> list[dict[str, str]]:
        return slash_helpers.local_slash_command_specs(locale=locale)

    @classmethod
    def _match_local_slash_commands(cls, prefix: str) -> list[dict[str, str]]:
        return slash_helpers.match_local_slash_commands(prefix)

    def _match_local_slash_commands_for_current_locale(self, prefix: str) -> list[dict[str, str]]:
        return slash_helpers.match_local_slash_commands_for_locale(
            prefix,
            locale=self._presentation.locale,
        )

    @classmethod
    def _complete_local_slash_command(cls, prefix: str) -> str | None:
        return slash_helpers.complete_local_slash_command(prefix)

    @classmethod
    def _merge_slash_matches(cls, *match_groups: list[dict[str, str]]) -> list[dict[str, str]]:
        return slash_helpers.merge_slash_matches(*match_groups)

    def _slash_command_catalog(self) -> list[dict[str, str]]:
        return slash_helpers.slash_command_catalog(
            self.runtime,
            local_slash_specs=slash_helpers.local_slash_command_specs(
                locale=self._presentation.locale
            ),
            merge_slash_matches_fn=self._merge_slash_matches,
        )

    def _slash_command_spec(self, command_name: str) -> dict[str, str] | None:
        return slash_helpers.slash_command_spec(
            command_name,
            slash_command_catalog_fn=self._slash_command_catalog,
        )

    @staticmethod
    def _active_nonspace_span(text: str, cursor_pos: int) -> tuple[int, int] | None:
        return slash_helpers.active_nonspace_span(text, cursor_pos)

    def _slash_completion_context(self) -> SlashCompletionContext | None:
        return slash_helpers.slash_completion_context(self)

    @staticmethod
    def _usage_flag_names(usage: str) -> list[str]:
        return slash_helpers.usage_flag_names(usage)

    def _current_provider_name(self) -> str | None:
        return slash_helpers.current_provider_name(self.runtime)

    def _available_provider_names(self) -> list[str]:
        return slash_helpers.available_provider_names(self.runtime)

    def _available_model_names(self, provider_name: str | None = None) -> list[str]:
        return slash_helpers.available_model_names(self.runtime, provider_name=provider_name)

    @staticmethod
    def _slash_pending_flag(command_name: str, completed_tokens: tuple[str, ...]) -> str | None:
        return slash_helpers.slash_pending_flag(command_name, completed_tokens)

    def _slash_command_available_during_busy(self, text_or_name: str) -> bool:
        candidate = str(text_or_name or "").strip()
        if not candidate:
            return False
        if not candidate.startswith("/"):
            context = self._slash_completion_context()
            if context is not None and context.mode == "slash_arg":
                command_name = str(context.command_name or "").strip().lower().lstrip("/")
                requested_name = candidate.lower().lstrip("/")
                if command_name and requested_name == command_name:
                    current_text = str(self._current_prompt_text() or "").strip()
                    if current_text.startswith("/"):
                        candidate = current_text
        return slash_helpers.slash_command_available_during_busy(candidate)

    @classmethod
    def _slash_flag_value_candidates(cls, command_name: str, flag_name: str) -> tuple[str, ...]:
        return slash_helpers.slash_flag_value_candidates(command_name, flag_name)

    @staticmethod
    def _completed_arg_tokens(context: SlashCompletionContext) -> tuple[str, ...]:
        return slash_helpers.completed_arg_tokens(context)

    def _slash_positional_candidates(
        self,
        command_name: str,
        completed_tokens: tuple[str, ...],
    ) -> list[tuple[str, str]]:
        return slash_helpers.slash_positional_candidates(
            command_name,
            completed_tokens,
            runtime=self.runtime,
        )

    def _slash_flag_candidates(self, command_name: str) -> list[tuple[str, str]]:
        return slash_helpers.slash_flag_candidates(
            command_name,
            slash_command_spec_getter=self._slash_command_spec,
        )

    def _slash_argument_matches(self, context: SlashCompletionContext) -> list[dict[str, str]]:
        return slash_helpers.slash_argument_matches(
            context,
            runtime=self.runtime,
            slash_command_spec_getter=self._slash_command_spec,
            slash_completion_replacement=self._slash_completion_replacement,
            locale=self._presentation.locale,
        )

    def _slash_completion_replacement(
        self,
        *,
        replace_start: int,
        replace_end: int,
        replacement: str,
    ) -> tuple[str, int]:
        return slash_helpers.slash_completion_replacement(
            self,
            replace_start=replace_start,
            replace_end=replace_end,
            replacement=replacement,
        )

    def _apply_slash_completion_item(self, item: dict[str, str]) -> bool:
        insert_text = str(item.get("insert_text") or "")
        if not insert_text:
            return False
        continue_completion = str(item.get("continue_completion") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._set_prompt_text(insert_text)
        self._suppressed_slash_popup_text = (
            insert_text
            if str(item.get("completion_mode") or "").strip().lower() == "slash_arg"
            and not continue_completion
            else None
        )
        try:
            cursor_pos = max(0, int(str(item.get("cursor_pos") or len(insert_text)).strip()))
        except ValueError:
            cursor_pos = len(insert_text)
        composer = self.query_one("#prompt_composer", PromptComposer)
        composer._cursor_pos = max(0, min(cursor_pos, len(insert_text)))
        composer._selection_anchor = None
        composer._preferred_column = None
        composer.refresh(repaint=True, layout=False)
        self.on_prompt_composer_changed()
        self._focus_input()
        return True

    def _handle_local_slash_command(self, text: str, *, attachments=None) -> bool:
        return slash_helpers.handle_local_slash_command(self, text, attachments=attachments)

    def _handle_local_lang_command(self, arg_text: str) -> None:
        slash_helpers.handle_local_lang_command(
            self,
            arg_text,
            save_preferences_fn=save_user_presentation_preferences,
        )

    def _handle_local_theme_command(self, arg_text: str) -> None:
        slash_helpers.handle_local_theme_command(
            self,
            arg_text,
            save_preferences_fn=save_user_presentation_preferences,
        )

    def _handle_local_setup_command(self, arg_text: str) -> bool:
        return slash_helpers.handle_local_setup_command(self, arg_text)

    def _handle_local_plan_command(self, arg_text: str, *, attachments=None) -> bool:
        return slash_helpers.handle_local_plan_command(
            self,
            arg_text,
            attachments=attachments,
        )

    def _handle_local_tab_rename_command(self, arg_text: str) -> bool:
        return slash_helpers.handle_local_tab_rename_command(self, arg_text)

    def _handle_local_tab_new_command(self, arg_text: str) -> bool:
        return slash_helpers.handle_local_tab_new_command(self, arg_text)

    def _handle_local_approval_inbox_command(self, arg_text: str) -> bool:
        return slash_helpers.handle_local_approval_inbox_command(self, arg_text)

    def _handle_local_preview_command(self, arg_text: str) -> bool:
        return slash_helpers.handle_local_preview_command(self, arg_text)

    def _handle_local_fork_command(self) -> bool:
        mgr = getattr(self, "_tab_manager", None)
        if mgr is None:
            return True
        active = mgr.active_tab_id
        tab_id = mgr.fork_tab(active)
        if not tab_id:
            write_notice = getattr(self, "_write_system_notice", None)
            if callable(write_notice):
                write_notice(self._t("system.tab_fork_failed"))
            return True
        self._focus_input()
        self._refresh_top_title_bar()
        return True

    def _handle_local_master_command(self, arg_text: str) -> bool:
        return slash_helpers.handle_local_master_command(self, arg_text)

    def _handle_local_fork_child_command(self, arg_text: str) -> bool:
        return slash_helpers.handle_local_fork_child_command(self, arg_text)

    def _handle_local_close_command(self) -> bool:
        mgr = getattr(self, "_tab_manager", None)
        if mgr is None:
            return False
        active = mgr.active_tab_id
        result = mgr.close_tab(active)
        if result is None:
            return False
        self._refresh_top_title_bar()
        self._focus_input()
        return True

    def _resolve_effective_presentation(self) -> PresentationSettings:
        return slash_helpers.resolve_effective_presentation(
            cwd=self._workspace_root,
            lang=self._presentation_cli_language,
            theme_id=self._presentation_cli_theme_id,
        )

    @staticmethod
    def _desired_locale_for_preference(value: str) -> str:
        return slash_helpers.desired_locale_for_preference(value)

    def _lang_override_source(self, desired_locale: str) -> str | None:
        return slash_helpers.lang_override_source(
            presentation_locale=self._presentation.locale,
            desired_locale=desired_locale,
            presentation_cli_language=self._presentation_cli_language,
            workspace_root=self._workspace_root,
        )

    def _theme_override_source(self, desired_theme_id: str) -> str | None:
        return slash_helpers.theme_override_source(
            presentation_theme_id=self._presentation.theme_id,
            desired_theme_id=desired_theme_id,
            presentation_cli_theme_id=self._presentation_cli_theme_id,
            workspace_root=self._workspace_root,
        )

    def _update_completion_popup(self) -> None:
        slash_helpers.update_completion_popup(self)

    def _slash_query(self) -> str | None:
        return slash_helpers.slash_query(self)

    def _update_slash_popup(self) -> None:
        slash_helpers.update_slash_popup(self)

    def _update_file_popup(self, query: str) -> None:
        slash_helpers.update_file_popup(self, query)


# Backward-compatible test import alias.
_SlashCompletionContext = SlashCompletionContext
