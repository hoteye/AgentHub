from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LocalSlashCommand:
    name: str
    arg_text: str


@dataclass(frozen=True, slots=True)
class PopupState:
    matches: list[dict[str, str]]
    selected_index: int
    query: str
    mode: str
    visible: bool


@dataclass(frozen=True, slots=True)
class LocalPreferenceCommandState:
    action: str
    value: str
    supported: str


def parse_local_slash_command(text: str) -> LocalSlashCommand | None:
    first_line = str(text or "").splitlines()[0].strip()
    match = re.match(r"^/([A-Za-z0-9_-]+)\b(.*)$", first_line)
    if match is None:
        return None
    return LocalSlashCommand(
        name=str(match.group(1) or "").strip().lower(),
        arg_text=str(match.group(2) or "").strip(),
    )


def handle_local_slash_command(
    text: str,
    *,
    handle_lang_fn: Callable[[str], None],
    handle_theme_fn: Callable[[str], None],
    handle_setup_fn: Callable[[str], bool],
    handle_plan_fn: Callable[[str], bool],
    handle_tab_rename_fn: Callable[[str], bool] | None = None,
    handle_tab_new_fn: Callable[[str], bool] | None = None,
    handle_approval_inbox_fn: Callable[[str], bool] | None = None,
    handle_preview_fn: Callable[[str], bool] | None = None,
    handle_fork_fn: Callable[[], bool] | None = None,
    handle_master_fn: Callable[[str], bool] | None = None,
    handle_fork_child_fn: Callable[[str], bool] | None = None,
    handle_close_fn: Callable[[], bool] | None = None,
) -> bool:
    command = parse_local_slash_command(text)
    if command is None:
        return False
    if command.name == "lang":
        handle_lang_fn(command.arg_text)
        return True
    if command.name == "theme":
        handle_theme_fn(command.arg_text)
        return True
    if command.name == "setup":
        return bool(handle_setup_fn(command.arg_text))
    if command.name == "plan":
        return bool(handle_plan_fn(command.arg_text))
    if command.name == "tab_rename" and handle_tab_rename_fn is not None:
        return bool(handle_tab_rename_fn(command.arg_text))
    if command.name == "tab_new" and handle_tab_new_fn is not None:
        return bool(handle_tab_new_fn(command.arg_text))
    if command.name == "approval_inbox" and handle_approval_inbox_fn is not None:
        return bool(handle_approval_inbox_fn(command.arg_text))
    if command.name == "preview" and handle_preview_fn is not None:
        return bool(handle_preview_fn(command.arg_text))
    if command.name == "fork" and handle_fork_fn is not None:
        return bool(handle_fork_fn())
    if command.name == "master" and handle_master_fn is not None:
        return bool(handle_master_fn(command.arg_text))
    if command.name == "fork_child" and handle_fork_child_fn is not None:
        return bool(handle_fork_child_fn(command.arg_text))
    if command.name == "close" and handle_close_fn is not None:
        return bool(handle_close_fn())
    return False


def resolve_lang_command_state(
    arg_text: str,
    *,
    current_locale: str,
    supported_locales: tuple[str, ...],
    auto_locale: str,
    normalize_locale_id_fn: Callable[[str], str | None],
) -> LocalPreferenceCommandState:
    value = str(arg_text or "").strip()
    supported = ", ".join([*supported_locales, auto_locale])
    if not value:
        return LocalPreferenceCommandState(
            action="status", value=current_locale, supported=supported
        )
    normalized = normalize_locale_id_fn(value)
    if normalized not in {*supported_locales, auto_locale}:
        return LocalPreferenceCommandState(action="invalid", value=value, supported=supported)
    return LocalPreferenceCommandState(action="save", value=normalized, supported=supported)


def resolve_theme_command_state(
    arg_text: str,
    *,
    current_theme_id: str,
    supported_themes: tuple[str, ...],
) -> LocalPreferenceCommandState:
    value = str(arg_text or "").strip().lower()
    supported = ", ".join(supported_themes)
    if not value:
        return LocalPreferenceCommandState(
            action="status", value=current_theme_id, supported=supported
        )
    if value not in supported_themes:
        return LocalPreferenceCommandState(action="invalid", value=value, supported=supported)
    return LocalPreferenceCommandState(action="save", value=value, supported=supported)


def desired_locale_for_preference(
    value: str,
    *,
    auto_locale: str,
    detect_system_locale_fn: Callable[[], str],
) -> str:
    return detect_system_locale_fn() if value == auto_locale else value


def lang_override_source(
    *,
    presentation_locale: str,
    desired_locale: str,
    presentation_cli_language: str | None,
    normalize_locale_id_fn: Callable[[str], str | None],
    project_override_path_getter: Callable[[str], str | None],
) -> str | None:
    if presentation_locale == desired_locale:
        return None
    if normalize_locale_id_fn(str(presentation_cli_language or "")) is not None:
        return "--lang"
    return project_override_path_getter("lang")


def theme_override_source(
    *,
    presentation_theme_id: str,
    desired_theme_id: str,
    presentation_cli_theme_id: str | None,
    project_override_path_getter: Callable[[str], str | None],
) -> str | None:
    if presentation_theme_id == desired_theme_id:
        return None
    if str(presentation_cli_theme_id or "").strip():
        return "--theme"
    return project_override_path_getter("theme")


def handle_local_lang_command(
    arg_text: str,
    *,
    supported_locales: tuple[str, ...],
    auto_locale: str,
    normalize_locale_id_fn: Callable[[str], str | None],
    user_config_path_getter: Callable[[], str],
    save_preferences_fn: Callable[..., str],
    resolve_effective_presentation_fn: Callable[[], object],
    apply_presentation_fn: Callable[[object], None],
    current_locale_getter: Callable[[], str],
    desired_locale_for_preference_fn: Callable[[str], str],
    lang_override_source_getter: Callable[[str], str | None],
    translate_fn: Callable[..., str],
    write_notice_fn: Callable[[str], None],
) -> None:
    state = resolve_lang_command_state(
        arg_text,
        current_locale=current_locale_getter(),
        supported_locales=supported_locales,
        auto_locale=auto_locale,
        normalize_locale_id_fn=normalize_locale_id_fn,
    )
    if state.action == "status":
        write_notice_fn(
            translate_fn("system.lang_status", current=state.value, supported=state.supported)
        )
        return
    if state.action == "invalid":
        write_notice_fn(
            translate_fn("system.lang_invalid", value=state.value, supported=state.supported)
        )
        return
    config_path = user_config_path_getter()
    try:
        config_path = save_preferences_fn(lang=state.value)
    except OSError as exc:
        write_notice_fn(
            translate_fn("system.lang_save_failed", path=str(config_path), error=str(exc))
        )
        return
    apply_presentation_fn(resolve_effective_presentation_fn())
    desired_locale = desired_locale_for_preference_fn(state.value)
    override_source = lang_override_source_getter(desired_locale)
    if override_source is None:
        write_notice_fn(
            translate_fn(
                "system.lang_saved", current=current_locale_getter(), path=str(config_path)
            )
        )
        return
    write_notice_fn(
        translate_fn(
            "system.lang_saved_overridden",
            path=str(config_path),
            current=current_locale_getter(),
            source=override_source,
        )
    )


def handle_local_theme_command(
    arg_text: str,
    *,
    supported_themes: tuple[str, ...],
    user_config_path_getter: Callable[[], str],
    save_preferences_fn: Callable[..., str],
    resolve_effective_presentation_fn: Callable[[], object],
    apply_presentation_fn: Callable[[object], None],
    current_theme_id_getter: Callable[[], str],
    theme_override_source_getter: Callable[[str], str | None],
    translate_fn: Callable[..., str],
    write_notice_fn: Callable[[str], None],
) -> None:
    state = resolve_theme_command_state(
        arg_text,
        current_theme_id=current_theme_id_getter(),
        supported_themes=supported_themes,
    )
    if state.action == "status":
        write_notice_fn(
            translate_fn("system.theme_status", current=state.value, supported=state.supported)
        )
        return
    if state.action == "invalid":
        write_notice_fn(
            translate_fn("system.theme_invalid", value=state.value, supported=state.supported)
        )
        return
    config_path = user_config_path_getter()
    try:
        config_path = save_preferences_fn(theme_id=state.value)
    except OSError as exc:
        write_notice_fn(
            translate_fn("system.theme_save_failed", path=str(config_path), error=str(exc))
        )
        return
    apply_presentation_fn(resolve_effective_presentation_fn())
    override_source = theme_override_source_getter(state.value)
    if override_source is None:
        write_notice_fn(
            translate_fn(
                "system.theme_saved", current=current_theme_id_getter(), path=str(config_path)
            )
        )
        return
    write_notice_fn(
        translate_fn(
            "system.theme_saved_overridden",
            path=str(config_path),
            current=current_theme_id_getter(),
            source=override_source,
        )
    )


def popup_hidden_state(*, mode: str = "slash") -> PopupState:
    return PopupState(matches=[], selected_index=0, query="", mode=mode, visible=False)


def popup_state(
    matches: list[dict[str, str]],
    *,
    selected_index: int,
    query: str,
    mode: str,
) -> PopupState:
    normalized_matches = [dict(item) for item in matches]
    if not normalized_matches:
        return popup_hidden_state(mode=mode)
    return PopupState(
        matches=normalized_matches,
        selected_index=clamp_selection_index(selected_index, len(normalized_matches)),
        query=str(query or ""),
        mode=mode,
        visible=True,
    )


def slash_popup_state_for_context(
    *,
    current_text: str,
    suppressed_text: str | None,
    context: Any | None,
    slash_argument_matches: list[dict[str, str]],
    slash_command_matches: list[dict[str, str]],
    selected_index: int,
) -> PopupState:
    if should_suppress_slash_popup(current_text=current_text, suppressed_text=suppressed_text):
        return popup_hidden_state()
    if context is None:
        return popup_hidden_state()
    matches = slash_argument_matches if context.mode == "slash_arg" else slash_command_matches
    return popup_state(
        matches,
        selected_index=selected_index,
        query=context.query,
        mode=context.mode,
    )


def should_suppress_slash_popup(*, current_text: str, suppressed_text: str | None) -> bool:
    return suppressed_text is not None and current_text == suppressed_text


def clamp_selection_index(index: int, count: int) -> int:
    if count <= 0:
        return 0
    return max(0, min(index, count - 1))


def cycle_selection_index(index: int, *, offset: int, count: int) -> int:
    if count <= 0:
        return 0
    return (index + offset) % count


def moved_popup_selection(
    *,
    has_file_popup: bool,
    file_selected_index: int,
    file_matches: list[dict[str, str]],
    slash_selected_index: int,
    slash_matches: list[dict[str, str]],
    offset: int,
) -> tuple[str, int]:
    if has_file_popup:
        return "file", cycle_selection_index(
            file_selected_index, offset=offset, count=len(file_matches)
        )
    if not slash_matches:
        return "none", 0
    return "slash", cycle_selection_index(
        slash_selected_index, offset=offset, count=len(slash_matches)
    )
