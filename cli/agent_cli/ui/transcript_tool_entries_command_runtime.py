from __future__ import annotations

from collections.abc import Callable

from cli.agent_cli.models import ActivityEvent
from cli.agent_cli.ui.transcript_history import TranscriptEntry
from cli.agent_cli.ui.transcript_structured_runtime import command_execution_payload, todo_payload


def todo_list_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
) -> TranscriptEntry:
    lines = ["• Todo List"]
    todo_lines: list[str] = []
    todos: list[dict[str, object]] = []
    for raw_entry in list(item.get("items") or []):
        if not isinstance(raw_entry, dict):
            continue
        text = str(raw_entry.get("text") or "").strip()
        if not text:
            continue
        completed = bool(raw_entry.get("completed"))
        marker = "✔" if completed else "□"
        todos.append({"text": text, "completed": completed})
        todo_lines.append(f"{marker} {text}")
    if todo_lines:
        first_line, *rest_lines = todo_lines
        lines.append(f"  └ {first_line}")
        lines.extend(f"    {line}" for line in rest_lines)
    else:
        lines.append("  └ (no steps provided)")
    return TranscriptEntry(
        kind="activity",
        layer="tool",
        lines=lines,
        status="info",
        activity_key=scope_activity_key(item_key),
        structured=todo_payload(todos=todos, source="turn_event"),
        render_mode="todo_list",
    )


def command_output_preview_lines(
    aggregated_output: str,
    *,
    command_output_max_lines: int,
) -> list[str]:
    raw_lines = [line.rstrip() for line in str(aggregated_output or "").splitlines()]
    if not any(line.strip() for line in raw_lines):
        return []
    if len(raw_lines) <= command_output_max_lines:
        return raw_lines
    head_count = 2
    tail_count = max(0, command_output_max_lines - head_count - 1)
    omitted = max(0, len(raw_lines) - head_count - tail_count)
    preview = [*raw_lines[:head_count], f"… +{omitted} lines"]
    if tail_count:
        preview.extend(raw_lines[-tail_count:])
    return preview


def command_output_line_count(aggregated_output: str) -> int:
    return len(str(aggregated_output or "").splitlines())


def command_duration_label(duration_ms: object) -> str:
    try:
        value = int(duration_ms)
    except (TypeError, ValueError):
        return ""
    if value < 0:
        return ""
    if value < 1000:
        return f"{value}ms"
    seconds = value / 1000
    return f"{seconds:.2f}s"


def command_execution_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
    command_output_max_lines: int,
    command_display_text_from_mapping_fn,
    unwrap_shell_wrapped_command_fn,
    command_output_preview_lines_fn,
) -> TranscriptEntry:
    source_command_text = str(item.get("command") or "").strip()
    unwrapped_command_text = (
        unwrap_shell_wrapped_command_fn(source_command_text) or source_command_text
    )
    command_text = command_display_text_from_mapping_fn(item) or unwrapped_command_text or "command"
    command_lines = command_text.splitlines() or [command_text]
    first_line = str(command_lines[0] or "").strip() or "command"
    status_text = str(item.get("status") or "").strip().lower()
    completed = status_text in {"completed", "failed"}
    lines = [f"• {'Ran' if completed else 'Running'} {first_line}"]
    for continuation in command_lines[1:]:
        lines.append(f"  │ {continuation}")
    output_lines = command_output_preview_lines_fn(
        str(item.get("aggregated_output") or ""),
        command_output_max_lines=command_output_max_lines,
    )
    output_line_count = command_output_line_count(str(item.get("aggregated_output") or ""))
    output_truncated = bool(output_lines and output_line_count > len(output_lines))
    if output_lines:
        first_output, *rest_output = output_lines
        lines.append(f"  └ {first_output}")
        lines.extend(f"    {line}" for line in rest_output)
    elif completed:
        lines.append("  └ (no output)")
    return TranscriptEntry(
        kind="activity",
        layer="tool",
        lines=lines,
        status="success" if status_text == "completed" else ("error" if completed else "running"),
        activity_key=scope_activity_key(item_key),
        structured=command_execution_payload(
            command_text=command_text,
            raw_command_text=unwrapped_command_text,
            command_lines=command_lines,
            output_lines=output_lines,
            status_text=status_text,
            exit_code=item.get("exit_code"),
            cwd=item.get("cwd"),
            duration_ms=item.get("duration_ms"),
            process_id=item.get("process_id"),
            output_truncated=output_truncated,
            output_line_count=output_line_count,
        ),
        render_mode="tool_command",
    )


def command_execution_exploration_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    event_type: str | None = None,
    exploration_entry_fn,
) -> TranscriptEntry | None:
    return exploration_entry_fn(item, item_key=item_key, event_type=event_type)


def command_execution_exploration_activity(
    item: dict[str, object],
    *,
    event_type: str | None = None,
    exploration_activity_fn,
) -> ActivityEvent | None:
    return exploration_activity_fn(item, event_type=event_type)
