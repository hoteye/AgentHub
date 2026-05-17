from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rich.cells import cell_len

from cli.agent_cli.ui.transcript_structured_access import (
    payload_input,
    payload_metadata,
    payload_state,
    payload_summary,
    payload_title,
    string_list,
)
from cli.agent_cli.ui.transcript_structured_visual_blocks import structured_tool_block_lines
from cli.agent_cli.ui.transcript_visual_rendering_helpers import wrap_prefixed_text

BlockLinesFn = Callable[..., list[str]]


def command_entry_block_lines(
    payload: dict[str, Any],
    *,
    width: int,
    block_lines_fn: BlockLinesFn = structured_tool_block_lines,
    metadata_detail_lines_fn: Callable[..., list[str]] | None = None,
    payload_input_fn: Callable[[dict[str, Any]], dict[str, Any]] = payload_input,
    payload_metadata_fn: Callable[[dict[str, Any]], dict[str, Any]] = payload_metadata,
    payload_state_fn: Callable[[dict[str, Any]], str] = payload_state,
    string_list_fn: Callable[[object], list[str]] = string_list,
) -> list[str]:
    input_payload = payload_input_fn(payload)
    metadata = payload_metadata_fn(payload)
    command_lines = string_list_fn(input_payload.get("command_lines"))
    command_text = str(
        input_payload.get("display_command") or input_payload.get("command") or ""
    ).strip()
    if not command_lines:
        command_lines = command_text.splitlines() or [command_text or "command"]
    output_lines = string_list_fn(metadata.get("output_lines"))
    if not output_lines:
        output_text = str(payload.get("output") or "")
        output_lines = [line.rstrip() for line in output_text.splitlines() if line.strip()]

    state = payload_state_fn(payload)
    completed = state in {"completed", "error"}
    header_word = "Ran" if completed else "Running"
    header_command = command_lines[0] if command_lines else command_text
    metadata_lines_fn = metadata_detail_lines_fn or command_metadata_detail_lines
    metadata_lines = [*command_lines[1:], *metadata_lines_fn(metadata, state=state)]
    return block_lines_fn(
        f"{header_word} {str(header_command or 'command').strip()}",
        width=width,
        metadata=metadata_lines,
        details=output_lines,
        empty_detail="(no output)" if completed else "",
    )


def command_metadata_detail_lines(
    metadata: dict[str, Any],
    *,
    state: str,
    duration_label_fn: Callable[[object], str] | None = None,
) -> list[str]:
    details: list[str] = []
    cwd = str(metadata.get("cwd") or "").strip()
    if cwd:
        details.append(f"cwd: {cwd}")
    exit_code = metadata.get("exit_code")
    if exit_code not in {None, ""} and state in {"completed", "error"}:
        details.append(f"exit: {exit_code}")
    label_fn = duration_label_fn or duration_label
    duration_text = label_fn(metadata.get("duration_ms"))
    if duration_text:
        details.append(f"duration: {duration_text}")
    process_id = str(metadata.get("process_id") or "").strip()
    if process_id and state == "running":
        details.append(f"session: {process_id}")
    output_line_count = metadata.get("output_line_count")
    if bool(metadata.get("output_truncated")) and output_line_count not in {None, ""}:
        details.append(f"output: {output_line_count} lines, preview shown")
    return details


def duration_label(duration_ms: object) -> str:
    try:
        value = int(duration_ms)
    except (TypeError, ValueError):
        return ""
    if value < 0:
        return ""
    if value < 1000:
        return f"{value}ms"
    return f"{value / 1000:.2f}s"


def todo_list_entry_block_lines(
    payload: dict[str, Any],
    *,
    width: int,
    wrap_text_fn: BlockLinesFn = wrap_prefixed_text,
    todo_body_lines_fn: Callable[..., list[str]] | None = None,
    payload_input_fn: Callable[[dict[str, Any]], dict[str, Any]] = payload_input,
    payload_metadata_fn: Callable[[dict[str, Any]], dict[str, Any]] = payload_metadata,
) -> list[str]:
    input_payload = payload_input_fn(payload)
    metadata = payload_metadata_fn(payload)
    todos = [item for item in input_payload.get("items") or [] if isinstance(item, dict)]
    plan_style = str(metadata.get("source") or "").strip() == "plan_activity"
    rendered_lines = wrap_text_fn(
        str(payload.get("title") or "Todo List"),
        first_prefix="• ",
        continuation_prefix="  ",
        width=width,
    )
    body_lines_fn = todo_body_lines_fn or todo_body_lines
    if todos:
        for index, todo in enumerate(todos):
            marker = "" if plan_style else ("✔ " if bool(todo.get("completed")) else "□ ")
            branch_prefix = "  └ " if index == 0 else "    "
            rendered_lines.extend(
                body_lines_fn(
                    f"{marker}{str(todo.get('text') or '').strip()}",
                    width=width,
                    branch_prefix=branch_prefix,
                )
            )
    else:
        rendered_lines.extend(
            body_lines_fn(
                "(no steps provided)",
                width=width,
                branch_prefix="  └ ",
            )
        )
    return rendered_lines


def todo_body_lines(
    text: str,
    *,
    width: int,
    branch_prefix: str,
    wrap_text_fn: BlockLinesFn = wrap_prefixed_text,
) -> list[str]:
    body_text = str(text or "")
    for marker in ("✔ ", "□ "):
        if body_text.startswith(marker):
            return wrap_text_fn(
                body_text[len(marker) :],
                first_prefix=f"{branch_prefix}{marker}",
                continuation_prefix=" " * (len(branch_prefix) + len(marker)),
                width=width,
            )
    continuation_prefix = " " * len(branch_prefix)
    return wrap_text_fn(
        body_text,
        first_prefix=branch_prefix,
        continuation_prefix=continuation_prefix,
        width=width,
    )


def command_exploration_entry_block_lines(
    payload: dict[str, Any],
    *,
    width: int,
    block_lines_fn: BlockLinesFn = structured_tool_block_lines,
    payload_header_fn: Callable[..., str] | None = None,
    exploration_detail_text_fn: Callable[[dict[str, Any]], str] | None = None,
    payload_input_fn: Callable[[dict[str, Any]], dict[str, Any]] = payload_input,
) -> list[str]:
    input_payload = payload_input_fn(payload)
    details = [item for item in input_payload.get("details") or [] if isinstance(item, dict)]
    header_fn = payload_header_fn or payload_header
    detail_text_fn = exploration_detail_text_fn or exploration_detail_text
    return block_lines_fn(
        header_fn(payload, default="Explored"),
        width=width,
        details=[detail_text_fn(detail) for detail in details],
    )


def exploration_detail_lines(
    detail: dict[str, Any],
    *,
    width: int,
    branch_prefix: str,
    exploration_detail_text_fn: Callable[[dict[str, Any]], str] | None = None,
    wrap_text_fn: BlockLinesFn = wrap_prefixed_text,
) -> list[str]:
    detail_text_fn = exploration_detail_text_fn or exploration_detail_text
    return wrap_text_fn(
        detail_text_fn(detail) or "(unknown)",
        first_prefix=branch_prefix,
        continuation_prefix=" " * len(branch_prefix),
        width=width,
    )


def exploration_detail_text(detail: dict[str, Any]) -> str:
    kind = str(detail.get("kind") or "").strip()
    subject = str(detail.get("subject") or "").strip()
    if kind == "list":
        return f"List {subject or '.'}".strip()
    if kind == "search":
        return f"Search {subject}".strip()
    if kind == "read":
        return f"Read {subject}".strip()
    return subject


def mcp_tool_entry_block_lines(
    payload: dict[str, Any],
    *,
    width: int,
    block_lines_fn: BlockLinesFn = structured_tool_block_lines,
    cell_len_fn: Callable[[str], int] = cell_len,
    payload_input_fn: Callable[[dict[str, Any]], dict[str, Any]] = payload_input,
    payload_metadata_fn: Callable[[dict[str, Any]], dict[str, Any]] = payload_metadata,
    payload_state_fn: Callable[[dict[str, Any]], str] = payload_state,
) -> list[str]:
    input_payload = payload_input_fn(payload)
    metadata = payload_metadata_fn(payload)
    invocation = str(input_payload.get("invocation") or "").strip()
    if not invocation:
        server = str(metadata.get("server") or "local").strip() or "local"
        tool_name = str(metadata.get("tool_name") or "tool").strip() or "tool"
        invocation = f"{server}.{tool_name}"
    state = payload_state_fn(payload)
    completed = state in {"completed", "error"}
    header_word = "Called" if completed else "Calling"
    detail = str(payload.get("output") or "").strip()
    header = f"{header_word} {invocation}".rstrip()
    inline_invocation = cell_len_fn(f"• {header}") <= max(1, int(width))
    metadata_lines = [] if inline_invocation else [invocation or "tool"]
    if not inline_invocation:
        header = header_word
    if detail:
        detail_lines = [detail]
    elif completed and state == "error":
        error_text = str(metadata.get("error") or "").strip()
        detail_lines = [f"Error: {error_text}"] if error_text else []
    else:
        detail_lines = []
    return block_lines_fn(
        header,
        width=width,
        metadata=metadata_lines,
        details=detail_lines,
    )


def artifact_entry_block_lines(
    payload: dict[str, Any],
    *,
    width: int,
    block_lines_fn: BlockLinesFn = structured_tool_block_lines,
    payload_input_fn: Callable[[dict[str, Any]], dict[str, Any]] = payload_input,
    payload_metadata_fn: Callable[[dict[str, Any]], dict[str, Any]] = payload_metadata,
    payload_summary_fn: Callable[[dict[str, Any]], str] = payload_summary,
) -> list[str]:
    input_payload = payload_input_fn(payload)
    metadata = payload_metadata_fn(payload)
    title = payload_summary_fn(payload) or str(payload.get("title") or "").strip() or "Artifact"
    subject = (
        str(input_payload.get("subject") or "").strip()
        or str(metadata.get("subject") or "").strip()
    )
    state = str(metadata.get("state") or payload.get("state") or "").strip()
    return block_lines_fn(
        title,
        width=width,
        metadata=[f"state: {state}"] if state else [],
        details=[subject] if subject and subject not in title else [],
    )


def payload_header(
    payload: dict[str, Any],
    *,
    default: str,
    payload_title_fn: Callable[[dict[str, Any]], str] | None = None,
) -> str:
    title_fn = payload_title_fn or payload_title
    header = title_fn(payload) or str(payload.get("title") or "").strip()
    if not header:
        header = str(default or "").strip()
    for prefix in ("• ", "✗ ", "⌕ ", "◆ ", "▸ ", "□ ", "◦ "):
        if header.startswith(prefix):
            return header[len(prefix) :].strip() or default
    return header or default
