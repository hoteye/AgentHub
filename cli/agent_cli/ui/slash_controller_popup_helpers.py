from __future__ import annotations

from typing import Any

from textual.css.query import NoMatches

from cli.agent_cli.slash_surface import pending_value_keyword as surface_pending_value_keyword
from cli.agent_cli.ui import slash_completion_pure_helpers_runtime, slash_controller_popup_runtime
from cli.agent_cli.ui.widgets import SlashCommandPopup


def update_completion_popup(controller: Any) -> None:
    if _is_browsing_prompt_history(controller):
        _clear_completion_popup(controller)
        return
    file_query = controller._file_query()
    if file_query is not None:
        update_file_popup(controller, file_query)
        return
    controller._file_matches = []
    controller._file_selected_index = 0
    update_slash_popup(controller)


def slash_query(controller: Any) -> str | None:
    context = controller._slash_completion_context()
    if context is None:
        return None
    return context.query


def _is_browsing_prompt_history(controller: Any) -> bool:
    prompt_history = getattr(controller, "_prompt_history", None)
    should_handle = getattr(prompt_history, "should_handle_navigation", None)
    if not callable(should_handle):
        return False
    try:
        composer = controller.query_one("#prompt_composer")
    except Exception:
        return False
    try:
        return bool(
            should_handle(
                str(getattr(composer, "text", "") or ""),
                int(getattr(composer, "cursor_pos", 0) or 0),
            )
        )
    except Exception:
        return False


def _clear_completion_popup(controller: Any) -> None:
    controller._slash_matches = []
    controller._slash_selected_index = 0
    controller._slash_popup_mode = "slash"
    controller._file_matches, controller._file_selected_index = [], 0
    controller._slash_popup_signature = None
    try:
        popup = controller.query_one("#slash_popup", SlashCommandPopup)
    except NoMatches:
        return
    popup.set_items([], 0, "")
    popup.styles.display = "none"


def _command_name_for_match(item: dict[str, str]) -> str:
    command_name = str(item.get("name") or "").strip()
    if command_name:
        return command_name.split(":", 1)[0].strip()
    usage = str(item.get("usage") or "").strip()
    if usage.startswith("/"):
        return usage[1:].split(" ", 1)[0].strip()
    return ""


def _slash_popup_signature(
    context: Any | None,
    slash_argument_matches: list[dict[str, str]],
    slash_command_matches: list[dict[str, str]],
) -> tuple[Any, ...]:
    if context is None:
        return ("hidden",)
    matches = slash_argument_matches if context.mode == "slash_arg" else slash_command_matches
    return (
        str(context.mode or ""),
        str(getattr(context, "command_name", "") or ""),
        str(context.query or ""),
        tuple(
            (
                str(item.get("name") or ""),
                str(item.get("usage") or ""),
                str(item.get("insert_text") or ""),
            )
            for item in matches
        ),
    )


def _selected_index_for_slash_update(
    controller: Any,
    context: Any | None,
    slash_argument_matches: list[dict[str, str]],
    slash_command_matches: list[dict[str, str]],
) -> int:
    signature = _slash_popup_signature(
        context,
        slash_argument_matches,
        slash_command_matches,
    )
    previous_signature = getattr(controller, "_slash_popup_signature", None)
    controller._slash_popup_signature = signature
    if signature != previous_signature:
        if context is not None and context.mode == "slash_arg":
            current_tokens = _current_value_tokens_for_slash_arg_context(controller, context)
            if current_tokens:
                return slash_completion_pure_helpers_runtime.current_slash_arg_selection_index(
                    getattr(controller, "runtime", None),
                    command_name=str(getattr(context, "command_name", "") or ""),
                    matches=slash_argument_matches,
                    current_tokens=current_tokens,
                )
        if (
            context is not None
            and context.mode == "slash_arg"
            and not str(getattr(context, "query", "") or "").strip()
        ):
            return slash_completion_pure_helpers_runtime.current_slash_arg_selection_index(
                getattr(controller, "runtime", None),
                command_name=str(getattr(context, "command_name", "") or ""),
                matches=slash_argument_matches,
            )
        return 0
    try:
        return int(getattr(controller, "_slash_selected_index", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _current_value_tokens_for_slash_arg_context(controller: Any, context: Any) -> tuple[str, ...]:
    command_name = str(getattr(context, "command_name", "") or "").strip().lower()
    if not command_name:
        return ()
    completed_tokens = slash_completion_pure_helpers_runtime.completed_arg_tokens(context)
    value_field = _slash_arg_value_field(command_name, completed_tokens)
    runtime = getattr(controller, "runtime", None)
    if value_field == "provider":
        return slash_completion_pure_helpers_runtime.current_provider_tokens(runtime)
    if value_field == "model":
        return slash_completion_pure_helpers_runtime.current_model_tokens(runtime)
    if value_field == "reasoning-effort":
        if command_name == "model" and len(completed_tokens) == 1:
            selected_model = str(completed_tokens[0] or "").strip()
            if slash_completion_pure_helpers_runtime.model_name_matches_current(
                runtime,
                selected_model,
            ):
                return slash_completion_pure_helpers_runtime.current_reasoning_effort_tokens(
                    runtime
                )
            default_tokens = (
                slash_completion_pure_helpers_runtime.default_reasoning_effort_tokens_for_model(
                    runtime,
                    selected_model,
                    provider_name=slash_completion_pure_helpers_runtime.current_provider_name(
                        runtime
                    ),
                )
            )
            if default_tokens:
                return default_tokens
        return slash_completion_pure_helpers_runtime.current_reasoning_effort_tokens(runtime)
    if value_field == "lang":
        return _presentation_tokens(controller, "locale")
    if value_field == "theme":
        return _presentation_tokens(controller, "theme_id")
    return _runtime_policy_tokens(runtime, value_field)


def _slash_arg_value_field(command_name: str, completed_tokens: tuple[str, ...]) -> str:
    pending_field = (
        str(surface_pending_value_keyword(command_name, completed_tokens) or "").strip().lower()
    )
    if pending_field:
        return pending_field
    if command_name == "provider":
        return "provider"
    if command_name == "models":
        return "provider"
    if command_name == "model":
        if len(completed_tokens) == 1:
            return "reasoning-effort"
        return "model"
    if command_name == "lang":
        return "lang"
    if command_name == "theme":
        return "theme"
    return ""


def _presentation_tokens(controller: Any, attr_name: str) -> tuple[str, ...]:
    presentation = getattr(controller, "_presentation", None)
    value = str(getattr(presentation, attr_name, "") or "").strip()
    return (value,) if value else ()


def _runtime_policy_tokens(runtime: Any, value_field: str) -> tuple[str, ...]:
    status_getter = getattr(runtime, "runtime_policy_status", None)
    if not callable(status_getter):
        return ()
    try:
        status = dict(status_getter() or {})
    except Exception:
        return ()
    key = {
        "approval-policy": "approval_policy",
        "sandbox-mode": "sandbox_mode",
        "web-search-mode": "web_search_mode",
        "network-access": "network_access",
    }.get(str(value_field or "").strip().lower())
    if not key:
        return ()
    value = str(status.get(key) or "").strip()
    return (value,) if value else ()


def _disabled_slash_match_rows(
    controller: Any,
    context: Any,
    slash_argument_matches: list[dict[str, str]],
    command_matches: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    disabled_reason = str(getattr(controller, "_BUSY_SLASH_COMMAND_NOTICE", "") or "").strip()

    availability_checker = getattr(controller, "_slash_command_available_during_busy", None)

    def _is_available(command_name: str) -> bool:
        if not callable(availability_checker):
            return False
        try:
            return bool(availability_checker(command_name))
        except Exception:
            return False

    def _disabled_row(item: dict[str, str], *, command_name: str) -> dict[str, str]:
        row = dict(item)
        if _is_available(command_name):
            return row
        row["disabled"] = "true"
        if disabled_reason:
            row["disabled_reason"] = disabled_reason
        return row

    if context.mode == "slash_arg":
        command_name = str(context.command_name or "").strip()
        if not command_name and slash_argument_matches:
            command_name = _command_name_for_match(slash_argument_matches[0])
        spec = controller._slash_command_spec(command_name) if command_name else None
        if spec is None:
            return ([], [])
        if _is_available(command_name):
            return ([dict(item) for item in slash_argument_matches], [])
        return ([_disabled_row(dict(spec), command_name=command_name)], [])
    disabled_items: list[dict[str, str]] = []
    for item in command_matches:
        command_name = _command_name_for_match(item)
        disabled_items.append(_disabled_row(dict(item), command_name=command_name))
    return ([], disabled_items)


def update_slash_popup(controller: Any) -> None:
    try:
        popup = controller.query_one("#slash_popup", SlashCommandPopup)
    except NoMatches:
        return
    context = controller._slash_completion_context()
    arg_matches = controller._slash_argument_matches(context) if context is not None else []
    command_matches = (
        controller._merge_slash_matches(
            controller.runtime.slash_command_matches(context.query),
            (
                controller._match_local_slash_commands_for_current_locale(context.query)
                if callable(
                    getattr(controller, "_match_local_slash_commands_for_current_locale", None)
                )
                else controller._match_local_slash_commands(context.query)
            ),
        )
        if context is not None and context.mode != "slash_arg"
        else []
    )
    slash_commands_blocked = (
        bool(controller._slash_commands_blocked_by_pending_runtime_work())
        if callable(getattr(controller, "_slash_commands_blocked_by_pending_runtime_work", None))
        else controller._has_pending_runtime_work()
    )
    if slash_commands_blocked:
        selected_index = _selected_index_for_slash_update(
            controller,
            context,
            arg_matches,
            command_matches,
        )
        disabled_arg_matches, disabled_command_matches = (
            _disabled_slash_match_rows(controller, context, arg_matches, command_matches)
            if context is not None
            else ([], [])
        )
        controller._apply_slash_popup_state(
            popup,
            slash_controller_popup_runtime.slash_popup_state_for_context(
                current_text=controller._current_prompt_text(),
                suppressed_text=controller._suppressed_slash_popup_text,
                context=context,
                slash_argument_matches=disabled_arg_matches,
                slash_command_matches=disabled_command_matches,
                selected_index=selected_index,
            ),
        )
        return
    selected_index = _selected_index_for_slash_update(
        controller,
        context,
        arg_matches,
        command_matches,
    )
    state = slash_controller_popup_runtime.slash_popup_state_for_context(
        current_text=controller._current_prompt_text(),
        suppressed_text=controller._suppressed_slash_popup_text,
        context=context,
        slash_argument_matches=arg_matches,
        slash_command_matches=command_matches,
        selected_index=selected_index,
    )
    controller._apply_slash_popup_state(popup, state)


def update_file_popup(controller: Any, query: str) -> None:
    try:
        popup = controller.query_one("#slash_popup", SlashCommandPopup)
    except NoMatches:
        return
    controller._slash_matches, controller._slash_selected_index = [], 0
    matches = controller._file_reference_matches(query)
    if not matches and bool(getattr(controller, "_workspace_files_indexing", False)):
        matches = [{"path": "", "description": "indexing workspace files..."}]
    controller._apply_file_popup_state(
        popup,
        slash_controller_popup_runtime.popup_state(
            matches, selected_index=controller._file_selected_index, query=query, mode="file"
        ),
    )
