from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cli.agent_cli import command_execution_summary_projection_helpers_runtime as _projection_helpers
from cli.agent_cli import command_execution_summary_pure_helpers_runtime as _pure_helpers
from cli.agent_cli import command_execution_summary_summary_helpers_runtime as _summary_helpers


COMMAND_EXECUTION_SUMMARIES_KEY = "exploration_summaries"
COMMAND_DISPLAY_KEY = "command_display"
DEFAULT_COMMAND_DISPLAY_MAX_LINES = _pure_helpers.DEFAULT_COMMAND_DISPLAY_MAX_LINES
DEFAULT_COMMAND_DISPLAY_MAX_CHARS = _pure_helpers.DEFAULT_COMMAND_DISPLAY_MAX_CHARS


@dataclass(frozen=True, slots=True)
class CommandExecutionSummary:
    kind: str
    path: str | None = None
    query: str | None = None
    name: str | None = None

    def exploration_detail(self) -> tuple[str, str] | None:
        if self.kind == "list":
            return ("list", self.path or ".")
        if self.kind == "search":
            if self.query and self.path:
                return ("search", f"{self.query} in {self.path}")
            subject = self.query or self.path or ""
            return ("search", subject) if subject else None
        subject = self.name or self.path or ""
        return ("read", subject) if subject else None

    def detail_line(self) -> str:
        detail = self.exploration_detail()
        if detail is None:
            return ""
        kind, subject = detail
        label = "Read"
        if kind == "list":
            label = "List"
        elif kind == "search":
            label = "Search"
        return f"{label} {subject}".strip()

    def to_dict(self) -> dict[str, str]:
        data = {"kind": str(self.kind or "").strip()}
        if self.path:
            data["path"] = str(self.path)
        if self.query:
            data["query"] = str(self.query)
        if self.name:
            data["name"] = str(self.name)
        return data


def _coerce_summary(value: object) -> CommandExecutionSummary | None:
    return _summary_helpers.coerce_summary(
        value,
        summary_type=CommandExecutionSummary,
        build_summary_fn=CommandExecutionSummary,
    )


def shell_comment_label_from_command(command_text: str) -> str:
    return _pure_helpers.shell_comment_label_from_command(command_text)


def command_display_text_from_command(
    command_text: str,
    *,
    single_line: bool = False,
    max_lines: int = DEFAULT_COMMAND_DISPLAY_MAX_LINES,
    max_chars: int = DEFAULT_COMMAND_DISPLAY_MAX_CHARS,
) -> str:
    return _projection_helpers.command_display_text_from_command(
        command_text,
        single_line=single_line,
        max_lines=max_lines,
        max_chars=max_chars,
    )


def command_display_text_from_mapping(
    item: dict[str, Any] | None,
    *,
    single_line: bool = False,
    max_lines: int = DEFAULT_COMMAND_DISPLAY_MAX_LINES,
    max_chars: int = DEFAULT_COMMAND_DISPLAY_MAX_CHARS,
) -> str:
    return _projection_helpers.command_display_text_from_mapping(
        item,
        command_display_key=COMMAND_DISPLAY_KEY,
        single_line=single_line,
        max_lines=max_lines,
        max_chars=max_chars,
    )


def command_execution_summaries_from_command(command_text: str) -> list[CommandExecutionSummary] | None:
    return _summary_helpers.command_execution_summaries_from_command(
        command_text,
        build_summary_fn=CommandExecutionSummary,
    )


def command_execution_summaries_from_mapping(item: dict[str, Any] | None) -> list[CommandExecutionSummary] | None:
    return _summary_helpers.command_execution_summaries_from_mapping(
        item,
        summaries_key=COMMAND_EXECUTION_SUMMARIES_KEY,
        coerce_summary_fn=_coerce_summary,
        summaries_from_command_fn=command_execution_summaries_from_command,
    )


def command_execution_summary_dicts_from_mapping(item: dict[str, Any] | None) -> list[dict[str, str]] | None:
    return _summary_helpers.command_execution_summary_dicts_from_mapping(
        item,
        summaries_from_mapping_fn=command_execution_summaries_from_mapping,
    )


def populate_command_execution_summary_dicts(item: dict[str, Any] | None) -> dict[str, Any]:
    return _summary_helpers.populate_command_execution_summary_dicts(
        item,
        summaries_key=COMMAND_EXECUTION_SUMMARIES_KEY,
        summary_dicts_from_mapping_fn=command_execution_summary_dicts_from_mapping,
    )


def command_activity_params(
    item: dict[str, Any] | None,
    *,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _summary_helpers.command_activity_params(
        item,
        extra_params=extra_params,
        command_display_key=COMMAND_DISPLAY_KEY,
        summaries_key=COMMAND_EXECUTION_SUMMARIES_KEY,
        command_display_from_mapping_fn=command_display_text_from_mapping,
        summary_dicts_from_mapping_fn=command_execution_summary_dicts_from_mapping,
    )
