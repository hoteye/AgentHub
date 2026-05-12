from __future__ import annotations

from typing import Any

from cli.agent_cli import command_execution_summary_pure_helpers_runtime as _pure_helpers
from cli.agent_cli.ui import transcript_shell_exploration_command_runtime


DEFAULT_COMMAND_DISPLAY_MAX_LINES = _pure_helpers.DEFAULT_COMMAND_DISPLAY_MAX_LINES
DEFAULT_COMMAND_DISPLAY_MAX_CHARS = _pure_helpers.DEFAULT_COMMAND_DISPLAY_MAX_CHARS


def command_display_text_from_command(
    command_text: str,
    *,
    single_line: bool = False,
    max_lines: int = DEFAULT_COMMAND_DISPLAY_MAX_LINES,
    max_chars: int = DEFAULT_COMMAND_DISPLAY_MAX_CHARS,
) -> str:
    command = transcript_shell_exploration_command_runtime.unwrap_shell_wrapped_command(
        str(command_text or "").strip()
    )
    if not command:
        return ""
    label = _pure_helpers.shell_comment_label_from_command(command)
    source = label or _pure_helpers.compact_command_display_source(command) or command
    return _pure_helpers.truncate_command_text(
        source,
        max_lines=max_lines,
        max_chars=max_chars,
        single_line=single_line,
    )


def command_display_text_from_mapping(
    item: dict[str, Any] | None,
    *,
    command_display_key: str,
    single_line: bool = False,
    max_lines: int = DEFAULT_COMMAND_DISPLAY_MAX_LINES,
    max_chars: int = DEFAULT_COMMAND_DISPLAY_MAX_CHARS,
) -> str:
    raw_item = dict(item or {})
    command_text = str(raw_item.get("command") or "").strip()
    if command_text and _pure_helpers.mapping_prefers_verbatim_command_display(raw_item):
        source = _pure_helpers.verbatim_command_display_source(command_text) or command_text
        return _pure_helpers.truncate_command_text(
            source,
            max_lines=max_lines,
            max_chars=max_chars,
            single_line=single_line,
        )
    explicit = str(raw_item.get(command_display_key) or "").strip()
    if explicit:
        if single_line:
            return _pure_helpers.truncate_command_text(
                explicit,
                max_lines=max_lines,
                max_chars=max_chars,
                single_line=True,
            )
        return explicit
    return command_display_text_from_command(
        command_text,
        single_line=single_line,
        max_lines=max_lines,
        max_chars=max_chars,
    )
