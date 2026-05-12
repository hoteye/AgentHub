from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any


def format_plan_steps(detail: str) -> list[str]:
    steps: list[str] = []
    for raw_line in detail.splitlines():
        text = raw_line.strip()
        if not text:
            continue
        text = re.sub(r"^\d+[\.\)]\s*", "", text)
        if text:
            steps.append(text)
    return steps


def format_file_list_lines(
    *,
    summary: str,
    count_text: str,
    path_text: str,
) -> list[str]:
    lines = [summary]
    if path_text and count_text:
        label = "file" if count_text == "1" else "files"
        lines.append(f"  └ {path_text} ({count_text} {label})")
        return lines
    if count_text:
        label = "file" if count_text == "1" else "files"
        lines.append(f"  └ {count_text} {label}")
    elif path_text:
        lines.append(f"  └ {path_text}")
    return lines


def format_file_search_lines(
    *,
    summary: str,
    count_text: str,
    query_text: str,
    path_text: str,
) -> list[str]:
    lines = [summary]
    if query_text and count_text and path_text:
        label = "match" if count_text == "1" else "matches"
        lines.append(f"  └ {query_text} ({count_text} {label} in {path_text})")
        return lines
    if query_text and count_text:
        label = "match" if count_text == "1" else "matches"
        lines.append(f"  └ {query_text} ({count_text} {label})")
        return lines
    if count_text and path_text:
        label = "match" if count_text == "1" else "matches"
        lines.append(f"  └ {count_text} {label} in {path_text}")
        return lines
    if query_text:
        lines.append(f"  └ {query_text}")
        return lines
    if count_text:
        label = "match" if count_text == "1" else "matches"
        lines.append(f"  └ {count_text} {label}")
    return lines


def format_file_read_lines(
    *,
    summary: str,
    raw: str,
    read_subject: str,
) -> list[str]:
    lines = [summary]
    segments = [segment.strip() for segment in raw.split(" | ") if segment.strip()]
    lead = read_subject or (segments[0] if segments else raw)
    lines.append(f"  └ {lead}")
    return lines


def format_view_image_lines(
    *,
    summary: str,
    raw: str,
    path_text: str,
) -> list[str]:
    lines = [summary]
    segments = [segment.strip() for segment in raw.split(" | ") if segment.strip()]
    lead = path_text or (segments[0] if segments else raw)
    display_name = Path(lead).name or lead
    if display_name:
        lines.append(f"  └ {display_name}")
        lines.append("    state=image_ready")
    else:
        lines.append("  └ state=image_ready")
    return lines


def format_web_search_lines(
    *,
    summary: str,
    raw: str,
    query_text: str,
    count_text: str,
    max_results: int | None,
    format_ranked_result_fn: Callable[[str], str],
) -> list[str]:
    lines = [summary]
    raw_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if query_text:
        lines.append(f"  └ {query_text}")
        return lines
    if not raw_lines:
        if count_text:
            label = "result" if count_text == "1" else "results"
            lines.append(f"  └ {count_text} {label}")
        return lines
    ranked_results = [line for line in raw_lines if re.match(r"^\d+\.\s+", line)]
    if ranked_results:
        visible_limit = None
        if max_results == 0:
            visible_limit = 2
        elif isinstance(max_results, int) and max_results > 0:
            visible_limit = max_results
        total_results = len(ranked_results)
        visible_results = (
            ranked_results[:visible_limit] if visible_limit is not None else ranked_results
        )
        visible_count = len(visible_results)
        label = "result" if visible_count == 1 else "results"
        lines.append(f"  └ {visible_count} {label}")
        formatted_results = [format_ranked_result_fn(result) for result in visible_results]
        if visible_limit is None:
            lines.extend(f"    {result}" for result in formatted_results)
            return lines
        remaining = total_results - visible_count
        if remaining > 0:
            remaining_label = "result" if remaining == 1 else "results"
            lines.append(f"    ... {remaining} more {remaining_label}")
        else:
            lines.extend(f"    {result}" for result in formatted_results)
        return lines
    if count_text:
        label = "result" if count_text == "1" else "results"
        lines.append(f"  └ {count_text} {label}")
    return lines


def format_web_page_lines(
    *,
    summary: str,
    raw: str,
    ref_id: str,
    domain: str,
    title: str,
    url: str,
) -> list[str]:
    lines = [summary]
    segments = [segment.strip() for segment in raw.split(" | ") if segment.strip()]
    resolved_ref_id = ref_id or next(
        (segment for segment in segments if segment.startswith("page_")), ""
    )
    remainder = [
        segment
        for segment in segments
        if segment != resolved_ref_id
        and not segment.startswith("scope=")
        and not segment.startswith("links=")
        and not segment.startswith("preview=")
    ]
    resolved_domain = domain or (remainder[0] if len(remainder) >= 2 else "")
    resolved_title = title or (remainder[-1] if remainder else "")
    lead = resolved_title or resolved_domain or url or raw
    lines.append(f"  └ {lead}")
    return lines


def format_web_find_lines(
    *,
    summary: str,
    raw: str,
    count_value: str,
) -> list[str]:
    lines = [summary]
    if count_value:
        label = "match" if count_value == "1" else "matches"
        lines.append(f"  └ {count_value} {label}")
    else:
        lines.append(f"  └ {raw}")
    return lines


def format_apply_patch_lines(
    *,
    summary: str,
    count_text: str,
    path_text: str = "",
) -> list[str]:
    lines = [summary]
    if path_text and (summary.endswith("Created file") or summary.endswith("Overwrote file")):
        lines.append(f"  └ {Path(path_text).name or path_text}")
        return lines
    if count_text:
        label = "file" if count_text == "1" else "files"
        lines.append(f"  └ {count_text} {label} changed")
    return lines


def format_patch_approval_lines(
    *,
    summary: str,
    approval_id: str,
    count_text: str,
    commands: list[str] | None = None,
) -> list[str]:
    lines = [summary]
    if approval_id and count_text:
        label = "file" if count_text == "1" else "files"
        lines.append(f"  └ {approval_id} ({count_text} {label})")
    elif approval_id:
        lines.append(f"  └ {approval_id}")
    lines.extend(f"    {command}" for command in list(commands or []) if str(command).strip())
    return lines


def format_shell_approval_lines(
    *,
    summary: str,
    approval_id: str,
    command_text: str,
    commands: list[str] | None = None,
) -> list[str]:
    lines = [summary]
    if approval_id and command_text:
        lines.append(f"  └ {approval_id}")
        lines.append(f"    {command_text}")
    elif approval_id:
        lines.append(f"  └ {approval_id}")
    lines.extend(f"    {command}" for command in list(commands or []) if str(command).strip())
    return lines


def format_action_approval_lines(
    *,
    summary: str,
    approval_id: str,
    lead_text: str,
    commands: list[str] | None = None,
) -> list[str]:
    lines = [summary]
    if approval_id and lead_text:
        lines.append(f"  └ {approval_id}")
        lines.append(f"    {lead_text}")
    elif approval_id:
        lines.append(f"  └ {approval_id}")
    elif lead_text:
        lines.append(f"  └ {lead_text}")
    lines.extend(f"    {command}" for command in list(commands or []) if str(command).strip())
    return lines


def format_approval_list_lines(
    *,
    summary: str,
    count_text: str,
    status_text: str,
) -> list[str]:
    lines = [summary]
    if count_text and status_text:
        label = "approval" if count_text == "1" else "approvals"
        lines.append(f"  └ {count_text} {status_text} {label}")
    elif count_text:
        label = "approval" if count_text == "1" else "approvals"
        lines.append(f"  └ {count_text} {label}")
    return lines


def format_approval_decision_lines(
    *,
    summary: str,
    approval_id: str,
    continuation_status: str = "",
    raw: str,
    action_type: str = "",
    status_text: str = "",
    decision_type: str = "",
    command_text: str = "",
) -> list[str]:
    command_decision_line = _format_command_approval_decision_line(
        action_type=action_type,
        status_text=status_text,
        decision_type=decision_type,
        command_text=command_text,
    )
    if command_decision_line:
        return [command_decision_line]
    lines = [summary]
    if approval_id:
        lines.append(f"  └ {approval_id}")
        if continuation_status == "completed":
            lines.append("    Continuing after approval: completed")
        elif continuation_status:
            lines.append(f"    Continuing after approval: {continuation_status}")
        return lines
    raw_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if raw_lines:
        lines.append(f"  └ {raw_lines[0]}")
    if continuation_status == "completed":
        lines.append("    Continuing after approval: completed")
    elif continuation_status:
        lines.append(f"    Continuing after approval: {continuation_status}")
    return lines


def _format_command_approval_decision_line(
    *,
    action_type: str,
    status_text: str,
    decision_type: str,
    command_text: str,
) -> str:
    if str(action_type or "").strip() != "shell_command":
        return ""
    command = _truncate_inline(str(command_text or "").strip(), max_chars=96)
    if not command:
        return ""
    status = str(status_text or "").strip().lower()
    decision = str(decision_type or "").strip().lower()
    if status == "approved":
        if decision == "accept_for_session":
            return f"✔ You approved AgentHub to run {command} every time this session"
        if decision == "accept_with_execpolicy_amendment":
            return f"✔ You approved AgentHub to always run commands that start with {command}"
        return f"✔ You approved AgentHub to run {command} this time"
    if status == "rejected":
        if decision == "cancel":
            return f"✗ You canceled the request to run {command}"
        return f"✗ You did not approve AgentHub to run {command}"
    return ""


def _truncate_inline(value: str, *, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 4)].rstrip() + " ..."


def exploration_detail_item(
    event: Any,
    *,
    activity_code_fn: Callable[[Any], str],
    activity_param_text_fn: Callable[[Any, str], str],
    search_subject_for_event_fn: Callable[[Any], str],
    search_subject_fn: Callable[[str], str],
    read_subject_for_event_fn: Callable[[Any], str],
) -> tuple[str, str] | None:
    code = activity_code_fn(event)
    raw = str(event.detail or "").strip()
    running_tool = activity_param_text_fn(event, "tool_name")
    if code in {"dir.list", "file.list"} or running_tool in {"list_dir", "file_list"}:
        subject = activity_param_text_fn(event, "dir_path", "path") or "."
        return ("list", subject)
    if code in {"dir.search", "file.search"} or running_tool in {"grep_files", "file_search"}:
        subject = search_subject_for_event_fn(event) or search_subject_fn(raw)
        return ("search", subject) if subject else None
    if code == "file.read" or running_tool in {"read_file", "file_read"}:
        subject = activity_param_text_fn(event, "file_path", "path") or read_subject_for_event_fn(
            event
        )
        return ("read", subject) if subject else None
    return None


def format_activity_summary(
    event: Any,
    *,
    activity_code_fn: Callable[[Any], str],
    activity_param_text_fn: Callable[[Any, str], str],
    strip_activity_prefix_fn: Callable[[str, str], str],
) -> str:
    code = activity_code_fn(event)
    title = str(event.title or "").strip()
    marker = "✗" if event.status == "error" else "•"
    if code == "image.view" and event.status != "error":
        return "• Image ready"
    if code.startswith("interrupt.") or event.kind == "interrupt":
        return f"• {title or 'Execution interrupted'}"
    if code == "web.search" and event.status == "running":
        return f"• {title or 'Searching the web'}"
    if code == "command.run" or event.kind == "command":
        command_text = activity_param_text_fn(event, "command_display", "command")
        if event.status == "running":
            command = command_text or strip_activity_prefix_fn(title, "Running ")
            return f"• Running {command or 'command'}"
        if event.status == "success":
            command = command_text or strip_activity_prefix_fn(title, "Ran ")
            return f"• Ran {command or 'command'}"
        if event.status == "error":
            return f"✗ {title or 'Command failed'}"
    if (code == "tool.run" or event.kind == "tool") and event.status == "running":
        tool_name = activity_param_text_fn(event, "tool_name") or strip_activity_prefix_fn(
            title, "Running "
        )
        return f"• Running {tool_name or 'tool'}"
    if event.status == "running":
        subject = activity_param_text_fn(event, "tool_name", "command") or strip_activity_prefix_fn(
            title, "Running "
        )
        return f"• Running {subject or 'activity'}"
    return f"{marker} {title}" if title else ""
