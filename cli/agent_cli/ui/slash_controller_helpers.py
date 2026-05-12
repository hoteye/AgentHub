from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from cli.agent_cli.slash_commands import (
    builtin_slash_command_registry_rows as _builtin_slash_command_registry_rows,
)
from cli.agent_cli.slash_commands import (
    slash_command_available_during_busy as _slash_command_available_during_busy,
)
from cli.agent_cli.ui import (
    slash_completion_runtime,
    slash_controller_popup_helpers,
    slash_controller_runtime,
)
from cli.agent_cli.ui.composer import PromptComposer
from cli.agent_cli.ui.presentation import (  # noqa: F401
    AUTO_LOCALE,
    SUPPORTED_LOCALES,
)
from cli.agent_cli.ui.slash_controller_command_handlers import (  # noqa: F401
    handle_local_approval_inbox_command,
    handle_local_fork_child_command,
    handle_local_lang_command,
    handle_local_master_command,
    handle_local_plan_command,
    handle_local_preview_command,
    handle_local_setup_command,
    handle_local_slash_command,
    handle_local_tab_new_command,
    handle_local_tab_rename_command,
    handle_local_theme_command,
)
from cli.agent_cli.ui.slash_controller_presentation_helpers import (  # noqa: F401
    desired_locale_for_preference,
    lang_override_source,
    resolve_effective_presentation,
    theme_override_source,
)
from cli.agent_cli.ui.theme import builtin_theme_ids


@dataclass(frozen=True, slots=True)
class SlashCompletionContext:
    mode: str
    query: str
    line_prefix: str
    line_end: str
    replace_start: int
    replace_end: int
    command_name: str | None = None
    arg_tokens: tuple[str, ...] = ()
    current_token: str = ""
    ends_with_space: bool = False


SLASH_BROWSER_ACTIONS: tuple[str, ...] = (
    "status",
    "start",
    "stop",
    "open",
    "navigate",
    "snapshot",
    "screenshot",
    "pdf",
    "console",
    "errors",
    "requests",
    "highlight",
    "trace_start",
    "trace_stop",
    "cookies",
    "storage",
    "storage_state",
    "act",
    "upload",
    "dialog",
)
SLASH_REASONING_EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "default")
SLASH_APPROVAL_STATUSES: tuple[str, ...] = ("pending", "approved", "rejected")
PYTHON_TAB_ENGINE_ALIASES: frozenset[str] = frozenset({"", "python", "agenthub", "agenthub_python"})
CODEX_SIDECAR_TAB_ENGINE_ALIASES: frozenset[str] = frozenset(
    {"codex", "sidecar", "codex_sidecar", "openai", "openai_codex"}
)
LOCAL_TUI_SLASH_COMMANDS: tuple[str, ...] = (
    "lang",
    "theme",
    "setup",
    "plan",
    "tab_rename",
    "tab_new",
    "approval_inbox",
    "preview",
    "fork",
    "master",
    "fork_child",
    "close",
)


def _local_slash_command_specs(*, locale: str | None = None) -> list[dict[str, str]]:
    rows = _builtin_slash_command_registry_rows(locale=locale)
    by_name = {str(item.get("name") or "").strip(): dict(item) for item in rows}
    specs: list[dict[str, str]] = []
    for command_name in LOCAL_TUI_SLASH_COMMANDS:
        row = by_name.get(command_name)
        if row is None:
            continue
        specs.append(
            {
                "name": str(row.get("name") or ""),
                "usage": str(row.get("usage") or ""),
                "description": str(row.get("description") or ""),
            }
        )
    if specs:
        return specs
    # Fallback keeps the local command surface stable if registry build fails.
    return [
        {
            "name": "lang",
            "usage": f"/lang <{'|'.join([*SUPPORTED_LOCALES, AUTO_LOCALE])}>",
            "description": "switch the interactive TUI language for the current session",
        },
        {
            "name": "theme",
            "usage": f"/theme <{'|'.join(builtin_theme_ids())}>",
            "description": "switch the interactive TUI theme for the current session",
        },
        {
            "name": "setup",
            "usage": "/setup",
            "description": "open the simple API key provider setup form",
        },
        {
            "name": "plan",
            "usage": "/plan",
            "description": "switch to Plan mode",
        },
        {
            "name": "tab_rename",
            "usage": "/tab_rename [label]",
            "description": "rename the active TUI tab label, or clear the custom label when empty",
        },
        {
            "name": "tab_new",
            "usage": "/tab_new [python|codex|openai]",
            "description": "create a new TUI tab, optionally backed by the Codex sidecar runtime",
        },
        {
            "name": "approval_inbox",
            "usage": "/approval_inbox [go <tab_id>]",
            "description": "show pending approvals across TUI tabs, or switch to a tab for review",
        },
        {
            "name": "preview",
            "usage": "/preview [open|close|toggle|status]",
            "description": "open, close, toggle, or show the fixed split preview pane",
        },
        {
            "name": "fork",
            "usage": "/fork",
            "description": "fork the current tab into a new independent tab",
        },
        {
            "name": "master",
            "usage": "/master",
            "description": "mark the current tab as a visible master tab",
        },
        {
            "name": "fork_child",
            "usage": "/fork_child",
            "description": "fork the current master tab into a visible child tab",
        },
    ]


def local_slash_command_specs(*, locale: str | None = None) -> list[dict[str, str]]:
    return _local_slash_command_specs(locale=locale)


def match_local_slash_commands(prefix: str) -> list[dict[str, str]]:
    return slash_completion_runtime.match_local_slash_commands(
        prefix,
        local_slash_specs=_local_slash_command_specs(),
    )


def match_local_slash_commands_for_locale(
    prefix: str, *, locale: str | None = None
) -> list[dict[str, str]]:
    return slash_completion_runtime.match_local_slash_commands(
        prefix,
        local_slash_specs=_local_slash_command_specs(locale=locale),
    )


def complete_local_slash_command(prefix: str) -> str | None:
    return slash_completion_runtime.complete_local_slash_command(
        prefix,
        local_slash_specs=_local_slash_command_specs(),
    )


def merge_slash_matches(*match_groups: list[dict[str, str]]) -> list[dict[str, str]]:
    return slash_controller_runtime.merge_slash_matches(*match_groups)


def slash_command_catalog(
    runtime: Any,
    local_slash_specs: Sequence[dict[str, str]],
    merge_slash_matches_fn: Callable[..., list[dict[str, str]]],
) -> list[dict[str, str]]:
    return slash_controller_runtime.slash_command_catalog(
        runtime,
        local_slash_specs=local_slash_specs,
        merge_slash_matches_fn=merge_slash_matches_fn,
    )


def slash_command_spec(
    command_name: str,
    slash_command_catalog_fn: Callable[[], list[dict[str, str]]],
) -> dict[str, str] | None:
    return slash_controller_runtime.slash_command_spec(
        command_name,
        slash_command_catalog_fn=slash_command_catalog_fn,
    )


def active_nonspace_span(text: str, cursor_pos: int) -> tuple[int, int] | None:
    return slash_controller_runtime.active_nonspace_span(text, cursor_pos)


def slash_completion_context(controller: Any) -> SlashCompletionContext | None:
    composer = controller.query_one("#prompt_composer", PromptComposer)
    return slash_controller_runtime.slash_completion_context(
        full_text=composer.text,
        cursor_pos=composer.cursor_pos,
        build_context_fn=SlashCompletionContext,
        active_nonspace_span_fn=controller._active_nonspace_span,
    )


def usage_flag_names(usage: str) -> list[str]:
    return slash_completion_runtime.usage_flag_names(usage)


def current_provider_name(runtime: Any) -> str | None:
    return slash_completion_runtime.current_provider_name(runtime)


def available_provider_names(runtime: Any) -> list[str]:
    return slash_completion_runtime.available_provider_names(runtime)


def available_model_names(runtime: Any, provider_name: str | None = None) -> list[str]:
    return slash_completion_runtime.available_model_names(runtime, provider_name=provider_name)


def slash_pending_flag(command_name: str, completed_tokens: tuple[str, ...]) -> str | None:
    return slash_completion_runtime.slash_pending_flag(command_name, completed_tokens)


def slash_command_available_during_busy(text_or_name: str) -> bool:
    return _slash_command_available_during_busy(text_or_name)


def slash_flag_value_candidates(command_name: str, flag_name: str) -> tuple[str, ...]:
    return slash_completion_runtime.slash_flag_value_candidates(
        command_name,
        flag_name,
        reasoning_efforts=SLASH_REASONING_EFFORTS,
        approval_statuses=SLASH_APPROVAL_STATUSES,
    )


def completed_arg_tokens(context: SlashCompletionContext) -> tuple[str, ...]:
    return slash_completion_runtime.completed_arg_tokens(context)


def slash_positional_candidates(
    command_name: str,
    completed_tokens: tuple[str, ...],
    runtime: Any,
) -> list[tuple[str, str]]:
    return slash_completion_runtime.slash_positional_candidates(
        command_name,
        completed_tokens,
        runtime=runtime,
        browser_actions=SLASH_BROWSER_ACTIONS,
    )


def slash_flag_candidates(
    command_name: str, slash_command_spec_getter: Callable[[str], dict[str, str] | None]
) -> list[tuple[str, str]]:
    return slash_completion_runtime.slash_flag_candidates(
        command_name,
        slash_command_spec_getter=slash_command_spec_getter,
    )


def slash_argument_matches(
    context: SlashCompletionContext,
    runtime: Any,
    slash_command_spec_getter: Callable[[str], dict[str, str] | None],
    slash_completion_replacement: Callable[..., tuple[str, int]],
    locale: str | None = None,
) -> list[dict[str, str]]:
    return slash_completion_runtime.slash_argument_matches(
        context,
        runtime=runtime,
        slash_command_spec_getter=slash_command_spec_getter,
        slash_completion_replacement=slash_completion_replacement,
        browser_actions=SLASH_BROWSER_ACTIONS,
        reasoning_efforts=SLASH_REASONING_EFFORTS,
        approval_statuses=SLASH_APPROVAL_STATUSES,
        locale=locale,
    )


def slash_completion_replacement(
    controller: Any,
    replace_start: int,
    replace_end: int,
    replacement: str,
) -> tuple[str, int]:
    current = controller._current_prompt_text()
    line_break = current.find("\n")
    first_line_end = len(current) if line_break < 0 else line_break
    updated = current[:replace_start] + replacement + current[replace_end:]
    cursor_pos = replace_start + len(replacement)
    if replace_end > first_line_end:
        return updated, cursor_pos
    return updated, cursor_pos


def update_completion_popup(controller: Any) -> None:
    slash_controller_popup_helpers.update_completion_popup(controller)


def slash_query(controller: Any) -> str | None:
    return slash_controller_popup_helpers.slash_query(controller)


def update_slash_popup(controller: Any) -> None:
    slash_controller_popup_helpers.update_slash_popup(controller)


def update_file_popup(controller: Any, query: str) -> None:
    slash_controller_popup_helpers.update_file_popup(controller, query)
