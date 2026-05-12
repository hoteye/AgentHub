from __future__ import annotations

from cli.agent_cli.ui.transcript_history import TranscriptEntry


def entries_for_screen(
    entries: list[TranscriptEntry],
    *,
    screen_mode: str,
) -> list[TranscriptEntry]:
    if str(screen_mode or "").strip().lower() == "transcript":
        return list(entries)
    return build_prompt_projection(entries)


def build_prompt_projection(entries: list[TranscriptEntry]) -> list[TranscriptEntry]:
    projected: list[TranscriptEntry] = []
    tool_group: list[TranscriptEntry] = []
    tool_group_key: str | None = None

    def flush_tool_group() -> None:
        nonlocal tool_group, tool_group_key
        if not tool_group:
            return
        if len(tool_group) == 1:
            projected.append(tool_group[0])
            tool_group = []
            tool_group_key = None
            return
        projected.append(_summarize_tool_group(tool_group, group_key=str(tool_group_key or "tool")))
        tool_group = []
        tool_group_key = None

    for entry in list(entries or []):
        next_group_key = _collapsible_tool_group_key(entry)
        if next_group_key is not None:
            if tool_group and tool_group_key != next_group_key:
                flush_tool_group()
            tool_group.append(entry)
            tool_group_key = next_group_key
            continue
        flush_tool_group()
        projected.append(entry)
    flush_tool_group()
    return projected


def _is_collapsible_tool_noise(entry: TranscriptEntry) -> bool:
    if entry.kind != "activity":
        return False
    if entry.layer not in {"tool", "web"}:
        return False
    if entry.render_mode == "todo_list":
        return False
    if str(entry.status or "").strip().lower() == "error":
        return False
    header = _header_text(entry).lower()
    if not header:
        return False
    if header.startswith("✗ "):
        return False
    if "approval" in header:
        return False
    if "updated plan" in header:
        return False
    if "patch" in header:
        return False
    return True


def _collapsible_tool_group_key(entry: TranscriptEntry) -> str | None:
    if not _is_collapsible_tool_noise(entry):
        return None
    if entry.layer == "web":
        return _web_group_key(entry)
    if entry.render_mode == "tool_mcp":
        return "tool_call"
    if entry.render_mode == "tool_command":
        return _command_group_key(entry)
    if entry.exploration_details:
        exploration_kinds = {str(kind or "").strip().lower() for kind, _subject in list(entry.exploration_details or [])}
        if len(exploration_kinds) == 1:
            return next(iter(exploration_kinds))
    header = _header_text(entry).lower()
    if "background" in header or "worker" in header or "workflow" in header or "followup" in header:
        return "background"
    if "viewed image" in header:
        return "image"
    if "read" in header:
        return "read"
    if "search" in header or "grep" in header or "find" in header:
        return "search"
    if "list" in header:
        return "list"
    return "tool"


def _summarize_tool_group(entries: list[TranscriptEntry], *, group_key: str) -> TranscriptEntry:
    count = len(entries)
    title = f"• {_category_label(group_key, count)}"
    first_summary = _summary_detail_text(entries[0])
    lines = [title]
    if first_summary:
        lines.append(f"  └ {first_summary}")
        if count > 1:
            lines.append(f"    +{count - 1} more")
    elif count > 1:
        lines.append(f"  └ +{count - 1} more")
    child_ids = tuple(str(entry.entry_id or "").strip() for entry in entries if str(entry.entry_id or "").strip())
    group_start = child_ids[0] if child_ids else "start"
    group_end = child_ids[-1] if child_ids else "end"
    search_text = "\n".join(str(entry.search_text or _summary_detail_text(entry)).strip() for entry in entries if str(entry.search_text or _summary_detail_text(entry)).strip())
    return TranscriptEntry(
        kind="activity",
        layer=str(entries[0].layer or "tool"),
        lines=lines,
        status=_group_status(entries),
        render_mode="prompt_tool_group",
        entry_id=f"prompt-group:{group_key}:{group_start}:{group_end}:{count}",
        group_key=group_key,
        search_text=search_text,
        child_entry_ids=child_ids,
    )


def _web_group_key(entry: TranscriptEntry) -> str:
    header = _header_text(entry).lower()
    if "native web search" in header:
        return "native_web_search"
    if "local web search" in header:
        return "local_web_search"
    if "search" in header:
        return "web_search"
    if "find" in header:
        return "web_find"
    return "web"


def _command_group_key(entry: TranscriptEntry) -> str:
    command_text = _command_text(entry).lower()
    if not command_text:
        return "command"
    first_token = command_text.split()[0]
    if first_token in {"cat", "sed", "head", "tail", "less", "more", "awk"}:
        return "read"
    if first_token in {"rg", "grep", "ag", "fd", "find"}:
        return "search"
    if first_token in {"ls", "tree"}:
        return "list"
    if first_token in {"git", "wc", "stat", "file", "pwd"}:
        return "inspect"
    return "command"


def _category_label(category: str, count: int) -> str:
    if category == "read":
        return f"Read {count} file{'s' if count != 1 else ''}"
    if category == "search":
        return f"Searched {count} path{'s' if count != 1 else ''}"
    if category == "list":
        return f"Listed {count} path{'s' if count != 1 else ''}"
    if category == "inspect":
        return f"Ran {count} inspection command{'s' if count != 1 else ''}"
    if category == "image":
        return f"Viewed {count} image{'s' if count != 1 else ''}"
    if category == "background":
        return f"Background activity ({count} update{'s' if count != 1 else ''})"
    if category == "web":
        return f"Web activity ({count} update{'s' if count != 1 else ''})"
    if category == "native_web_search":
        return f"Native web search ({count} update{'s' if count != 1 else ''})"
    if category == "local_web_search":
        return f"Local web search ({count} update{'s' if count != 1 else ''})"
    if category == "web_search":
        return f"Web search ({count} update{'s' if count != 1 else ''})"
    if category == "web_find":
        return f"Web find ({count} update{'s' if count != 1 else ''})"
    if category == "command":
        return f"Shell activity ({count} update{'s' if count != 1 else ''})"
    if category == "tool_call":
        return f"Tool activity ({count} call{'s' if count != 1 else ''})"
    return f"Tool activity ({count} update{'s' if count != 1 else ''})"


def _group_status(entries: list[TranscriptEntry]) -> str:
    statuses = {str(entry.status or "").strip().lower() for entry in entries}
    if "error" in statuses or "failed" in statuses:
        return "error"
    if "running" in statuses:
        return "running"
    if "success" in statuses or "completed" in statuses:
        return "success"
    return "info"


def _summary_detail_text(entry: TranscriptEntry) -> str:
    if entry.render_mode == "web_search" and len(entry.lines) > 1:
        branch = str(entry.lines[1] or "").strip()
        if branch.startswith("└ "):
            return branch[2:].strip()
        if branch.startswith("└"):
            return branch[1:].strip()
        if branch:
            return branch
    if not entry.lines:
        return ""
    line = str(entry.lines[0] or "").strip()
    if line.startswith("• "):
        return line[2:].strip()
    return line


def _header_text(entry: TranscriptEntry) -> str:
    if not entry.lines:
        return ""
    return str(entry.lines[0] or "").strip()


def _command_text(entry: TranscriptEntry) -> str:
    header = _header_text(entry)
    for prefix in ("• Running ", "• Ran "):
        if header.startswith(prefix):
            return header[len(prefix) :].strip()
    return header
