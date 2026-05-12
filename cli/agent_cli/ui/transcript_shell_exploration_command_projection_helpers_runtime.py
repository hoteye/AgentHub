from __future__ import annotations

from typing import Callable, TypeVar

from cli.agent_cli.ui import transcript_shell_exploration_command_mapping_runtime
from cli.agent_cli.ui.transcript_shell_exploration_command_normalization_helpers_runtime import (
    _short_display_path,
    join_display_paths,
)
from cli.agent_cli.ui.transcript_shell_exploration_command_pure_helpers_runtime import (
    _awk_data_file_operand,
    _first_non_flag_operand,
    _parse_fd_query_and_path,
    _parse_find_query_and_path,
    _parse_grep_like,
    _sed_read_path,
    _single_non_flag_operand,
    _skip_flag_values,
)


SummaryT = TypeVar("SummaryT")


def stream_read_summary(
    tokens: list[str],
    *,
    stream_subject: str | None,
    build_summary_fn: Callable[..., SummaryT],
) -> SummaryT | None:
    subject = str(stream_subject or "").strip()
    if not tokens or not subject:
        return None
    head = str(tokens[0] or "").strip().lower()
    tail = tokens[1:]
    if head == "sed" and _sed_read_path(tail) is None and "-n" in tail:
        return build_summary_fn(kind="read", name=subject, path=subject)
    if head == "head":
        path = None
        for candidate in tail:
            if not str(candidate or "").startswith("-"):
                path = candidate
                break
        if path is None:
            return build_summary_fn(kind="read", name=subject, path=subject)
    if head == "tail":
        path = None
        for candidate in tail:
            if not str(candidate or "").startswith("-"):
                path = candidate
                break
        if path is None:
            return build_summary_fn(kind="read", name=subject, path=subject)
    return None


def bind_stream_subject(
    summary: SummaryT | None,
    *,
    stream_subject: str | None,
    build_summary_fn: Callable[..., SummaryT],
) -> SummaryT | None:
    if summary is None:
        return None
    subject = str(stream_subject or "").strip()
    kind = str(getattr(summary, "kind", "") or "").strip().lower()
    if not subject or not kind:
        return summary
    if kind == "search" and not str(getattr(summary, "path", "") or "").strip():
        return build_summary_fn(
            kind="search",
            query=str(getattr(summary, "query", "") or "").strip() or None,
            path=subject,
        )
    if kind == "read":
        name = str(getattr(summary, "name", "") or "").strip()
        path = str(getattr(summary, "path", "") or "").strip()
        if not name and not path:
            return build_summary_fn(kind="read", name=subject, path=subject)
    return summary


def parse_shell_segment(
    tokens: list[str],
    *,
    cwd: str | None,
    build_summary_fn: Callable[..., SummaryT],
) -> SummaryT | None:
    return transcript_shell_exploration_command_mapping_runtime.parse_shell_segment(
        tokens,
        cwd=cwd,
        build_summary_fn=build_summary_fn,
        first_non_flag_operand_fn=_first_non_flag_operand,
        skip_flag_values_fn=_skip_flag_values,
        display_list_subject_fn=lambda path: _display_list_subject(path, cwd=cwd),
        display_search_path_fn=lambda path: _display_search_path(path, cwd=cwd),
        display_read_name_fn=lambda path: _display_read_name(path, cwd=cwd),
        parse_grep_like_fn=_parse_grep_like,
        parse_fd_query_and_path_fn=_parse_fd_query_and_path,
        parse_find_query_and_path_fn=_parse_find_query_and_path,
        single_non_flag_operand_fn=_single_non_flag_operand,
        awk_data_file_operand_fn=_awk_data_file_operand,
        sed_read_path_fn=_sed_read_path,
    )


def _display_list_subject(path: str | None, *, cwd: str | None) -> str:
    if path is None and not cwd:
        return "."
    effective = join_display_paths(cwd, path or ".")
    if effective == ".":
        return "."
    return _short_display_path(effective)


def _display_search_path(path: str | None, *, cwd: str | None) -> str | None:
    text = str(path or "").strip()
    if not text:
        return None
    return _short_display_path(join_display_paths(cwd, text))


def _display_read_name(path: str, *, cwd: str | None) -> str:
    effective = join_display_paths(cwd, path)
    return _short_display_path(effective)
