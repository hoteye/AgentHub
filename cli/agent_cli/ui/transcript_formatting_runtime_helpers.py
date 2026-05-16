from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.ui import (
    approval_surface_runtime,
    transcript_formatting_activity_approval_runtime,
    transcript_formatting_activity_runtime,
)


def format_file_list_lines(
    event: Any, summary: str, raw: str, *, activity_param_text_fn: Callable[..., str]
) -> list[str]:
    del raw
    return transcript_formatting_activity_runtime.format_file_list_lines(
        summary=summary,
        count_text=activity_param_text_fn(event, "count"),
        path_text=activity_param_text_fn(event, "path", "dir_path"),
    )


def format_file_search_lines(
    event: Any, summary: str, raw: str, *, activity_param_text_fn: Callable[..., str]
) -> list[str]:
    del raw
    return transcript_formatting_activity_runtime.format_file_search_lines(
        summary=summary,
        count_text=activity_param_text_fn(event, "count"),
        query_text=activity_param_text_fn(event, "query", "pattern"),
        path_text=activity_param_text_fn(event, "path", "dir_path"),
    )


def format_file_read_lines(
    event: Any,
    summary: str,
    raw: str,
    *,
    read_subject_for_event_fn: Callable[[Any], str],
) -> list[str]:
    return transcript_formatting_activity_runtime.format_file_read_lines(
        summary=summary,
        raw=raw,
        read_subject=read_subject_for_event_fn(event),
    )


def format_view_image_lines(
    event: Any, summary: str, raw: str, *, activity_param_text_fn: Callable[..., str]
) -> list[str]:
    return transcript_formatting_activity_runtime.format_view_image_lines(
        summary=summary,
        raw=raw,
        path_text=activity_param_text_fn(event, "path"),
    )


def format_web_search_lines(
    event: Any,
    summary: str,
    raw: str,
    *,
    max_results: int | None,
    activity_param_text_fn: Callable[..., str],
    format_ranked_result_fn: Callable[[str], str],
) -> list[str]:
    return transcript_formatting_activity_runtime.format_web_search_lines(
        summary=summary,
        raw=raw,
        query_text=activity_param_text_fn(event, "query"),
        count_text=activity_param_text_fn(event, "count"),
        max_results=max_results,
        format_ranked_result_fn=format_ranked_result_fn,
    )


def format_web_page_lines(
    event: Any, summary: str, raw: str, *, activity_param_text_fn: Callable[..., str]
) -> list[str]:
    return transcript_formatting_activity_runtime.format_web_page_lines(
        summary=summary,
        raw=raw,
        ref_id=activity_param_text_fn(event, "ref_id"),
        domain=activity_param_text_fn(event, "source_domain"),
        title=activity_param_text_fn(event, "title"),
        url=activity_param_text_fn(event, "final_url", "url"),
    )


def format_web_find_lines(
    event: Any,
    summary: str,
    raw: str,
    *,
    activity_param_only_text_fn: Callable[..., str],
) -> list[str]:
    segments = [segment.strip() for segment in raw.split(" | ") if segment.strip()]
    count_value = activity_param_only_text_fn(event, "count") or next(
        (segment.partition("=")[2].strip() for segment in segments if segment.startswith("count=")),
        "",
    )
    return transcript_formatting_activity_runtime.format_web_find_lines(
        summary=summary,
        raw=raw,
        count_value=count_value,
    )


def format_apply_patch_lines(
    event: Any, summary: str, raw: str, *, activity_param_text_fn: Callable[..., str]
) -> list[str]:
    raw_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    file_count_line = next((line for line in raw_lines if line.startswith("files=")), "")
    count_text = activity_param_text_fn(event, "file_count") or (
        file_count_line.partition("=")[2].strip() if file_count_line else ""
    )
    path_line = next(
        (
            line
            for line in raw_lines
            if line and not line.startswith("files=") and not line.startswith("write_mode=")
        ),
        "",
    )
    return transcript_formatting_activity_runtime.format_apply_patch_lines(
        summary=summary,
        count_text=count_text,
        path_text=path_line,
    )


def format_patch_approval_lines(
    event: Any, summary: str, raw: str, *, activity_param_text_fn: Callable[..., str]
) -> list[str]:
    raw_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    approval_id = activity_param_text_fn(event, "approval_id") or (
        raw_lines[0] if raw_lines else ""
    )
    file_count_line = next((line for line in raw_lines if line.startswith("files=")), "")
    count_text = activity_param_text_fn(event, "file_count") or (
        file_count_line.partition("=")[2].strip() if file_count_line else ""
    )
    return transcript_formatting_activity_approval_runtime.format_patch_approval_lines(
        summary=summary,
        approval_id=approval_id,
        count_text=count_text,
        commands=approval_surface_runtime.approval_commands(
            approval_id=approval_id,
            raw=raw,
            allow_generic_fallback=False,
        ),
    )


def format_shell_approval_lines(
    event: Any, summary: str, raw: str, *, activity_param_text_fn: Callable[..., str]
) -> list[str]:
    raw_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    approval_id = activity_param_text_fn(event, "approval_id") or (
        raw_lines[0] if raw_lines else ""
    )
    command_text = activity_param_text_fn(event, "command") or (
        raw_lines[1] if len(raw_lines) >= 2 else ""
    )
    return transcript_formatting_activity_approval_runtime.format_shell_approval_lines(
        summary=summary,
        approval_id=approval_id,
        command_text=command_text,
        commands=approval_surface_runtime.approval_commands(
            approval_id=approval_id,
            raw=raw,
            allow_generic_fallback=False,
        ),
    )


def format_action_approval_lines(
    event: Any, summary: str, raw: str, *, activity_param_text_fn: Callable[..., str]
) -> list[str]:
    raw_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    approval_id = activity_param_text_fn(event, "approval_id") or (
        raw_lines[0] if raw_lines else ""
    )
    lead_text = activity_param_text_fn(event, "task", "summary") or (
        raw_lines[1] if len(raw_lines) >= 2 else ""
    )
    return transcript_formatting_activity_approval_runtime.format_action_approval_lines(
        summary=summary,
        approval_id=approval_id,
        lead_text=lead_text,
        commands=approval_surface_runtime.approval_commands(
            approval_id=approval_id,
            raw=raw,
            allow_generic_fallback=False,
        ),
    )


def format_approval_list_lines(
    event: Any, summary: str, raw: str, *, activity_param_text_fn: Callable[..., str]
) -> list[str]:
    del raw
    return transcript_formatting_activity_approval_runtime.format_approval_list_lines(
        summary=summary,
        count_text=activity_param_text_fn(event, "count"),
        status_text=activity_param_text_fn(event, "status"),
    )


def format_approval_decision_lines(
    event: Any, summary: str, raw: str, *, activity_param_text_fn: Callable[..., str]
) -> list[str]:
    return transcript_formatting_activity_approval_runtime.format_approval_decision_lines(
        summary=summary,
        approval_id=activity_param_text_fn(event, "approval_id"),
        continuation_status=activity_param_text_fn(event, "continuation_status"),
        raw=raw,
        action_type=activity_param_text_fn(event, "action_type"),
        status_text=activity_param_text_fn(event, "status"),
        decision_type=activity_param_text_fn(event, "decision_type"),
        command_text=activity_param_text_fn(event, "command"),
    )
