from __future__ import annotations

from cli.agent_cli.ui.transcript_history import TranscriptEntry
from cli.agent_cli.ui.transcript_structured_access import (
    first_summary_line as structured_first_summary_line,
)
from cli.agent_cli.ui.transcript_structured_access import (
    payload_code as structured_payload_code,
)
from cli.agent_cli.ui.transcript_structured_access import (
    payload_command_text as structured_payload_command_text,
)
from cli.agent_cli.ui.transcript_structured_access import (
    payload_exploration_details as structured_payload_exploration_details,
)
from cli.agent_cli.ui.transcript_structured_access import (
    payload_group_key as structured_payload_group_key,
)
from cli.agent_cli.ui.transcript_structured_access import (
    payload_input as structured_payload_input,
)
from cli.agent_cli.ui.transcript_structured_access import (
    payload_metadata as structured_payload_metadata,
)
from cli.agent_cli.ui.transcript_structured_access import (
    payload_name as structured_payload_name,
)
from cli.agent_cli.ui.transcript_structured_access import (
    payload_output as structured_payload_output,
)
from cli.agent_cli.ui.transcript_structured_access import (
    payload_state as structured_payload_state,
)
from cli.agent_cli.ui.transcript_structured_access import (
    payload_summary as structured_payload_summary,
)
from cli.agent_cli.ui.transcript_structured_access import (
    payload_title as structured_payload_title,
)
from cli.agent_cli.ui.transcript_structured_access import (
    structured_payload,
)


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
    payload = structured_payload(entry)
    if payload is not None:
        state = structured_payload_state(payload)
        if state in {"error", "failed"}:
            return False
        payload_kind = structured_payload_name(payload)
        code = structured_payload_code(payload)
        if payload_kind == "todo_list":
            return False
        if code.startswith("approval.") or code == "patch.apply":
            return False
        semantic_text = " ".join(
            part
            for part in (
                payload_kind,
                code,
                structured_payload_title(payload).lower(),
                str(structured_payload_metadata(payload).get("tool_name") or "").strip().lower(),
            )
            if part
        )
        if "approval" in semantic_text or "patch" in semantic_text:
            return False
        return True
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
    structured_key = _structured_group_key(entry)
    if structured_key:
        return structured_key
    if entry.layer == "web":
        return _web_group_key(entry)
    if entry.render_mode == "tool_mcp":
        return "tool_call"
    if entry.render_mode == "tool_command":
        return _command_group_key(entry)
    if entry.exploration_details:
        exploration_kinds = {
            str(kind or "").strip().lower()
            for kind, _subject in list(entry.exploration_details or [])
        }
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
    child_ids = tuple(
        str(entry.entry_id or "").strip() for entry in entries if str(entry.entry_id or "").strip()
    )
    group_start = child_ids[0] if child_ids else "start"
    group_end = child_ids[-1] if child_ids else "end"
    search_text = "\n".join(
        str(entry.search_text or _summary_detail_text(entry)).strip()
        for entry in entries
        if str(entry.search_text or _summary_detail_text(entry)).strip()
    )
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
    payload = structured_payload(entry)
    if payload is not None:
        name = structured_payload_name(payload)
        code = structured_payload_code(payload)
        input_payload = structured_payload_input(payload)
        title = structured_payload_title(payload).lower()
        backend = str(input_payload.get("backend") or "").strip().lower()
        if (
            bool(input_payload.get("provider_native"))
            or backend == "native"
            or title.startswith("native web search")
        ):
            return "native_web_search"
        if backend == "local" or title.startswith("local web search"):
            return "local_web_search"
        if "find" in {name, code} or name.endswith(".find") or code.endswith(".find"):
            return "web_find"
        if "search" in name or "search" in code:
            return "web_search"
        return "web"
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


def _structured_group_key(entry: TranscriptEntry) -> str | None:
    payload = structured_payload(entry)
    if payload is None:
        return None
    explicit_group_key = structured_payload_group_key(payload)
    if explicit_group_key:
        return explicit_group_key
    name = structured_payload_name(payload)
    code = structured_payload_code(payload)
    if entry.layer == "web" or code.startswith("web.") or name.startswith("web."):
        return _web_group_key(entry)
    if name == "mcp_tool_call":
        return "tool_call"
    if name == "command_execution":
        return _command_group_key(entry)
    if name == "command_exploration":
        exploration_kinds = {
            str(detail.get("kind") or "").strip().lower()
            for detail in structured_payload_exploration_details(payload)
            if str(detail.get("kind") or "").strip()
        }
        if len(exploration_kinds) == 1:
            return next(iter(exploration_kinds))
        return "tool"
    if name in {"view_image", "input_image_output"} or code == "image.view":
        return "image"
    if name in {"view_document", "document_output"}:
        return "document"
    if code in {"dir.list", "file.list"}:
        return "list"
    if code in {"dir.search", "file.search"}:
        return "search"
    if code == "file.read":
        return "read"
    if code == "command.run":
        return "tool"
    if "background" in name or "worker" in name or "workflow" in name or "followup" in name:
        return "background"
    return None


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
    if category == "document":
        return f"Viewed {count} document{'s' if count != 1 else ''}"
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
    structured_summary = _structured_summary_text(entry)
    if structured_summary:
        return structured_summary
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
    structured_command = _structured_command_text(entry)
    if structured_command:
        return structured_command
    header = _header_text(entry)
    for prefix in ("• Running ", "• Ran "):
        if header.startswith(prefix):
            return header[len(prefix) :].strip()
    return header


def _structured_command_text(entry: TranscriptEntry) -> str:
    return structured_payload_command_text(structured_payload(entry))


def _structured_summary_text(entry: TranscriptEntry) -> str:
    payload = structured_payload(entry)
    if payload is None:
        return ""
    explicit_summary = structured_payload_summary(payload)
    if explicit_summary:
        return explicit_summary
    name = structured_payload_name(payload)
    if name == "command_execution":
        command_text = structured_payload_command_text(payload)
        if not command_text:
            return ""
        state = structured_payload_state(payload)
        prefix = "Ran" if state in {"completed", "error"} else "Running"
        return f"{prefix} {structured_first_summary_line(command_text)}".strip()
    if name == "command_exploration":
        details = structured_payload_exploration_details(payload)
        if not details:
            return ""
        kind = str(details[0].get("kind") or "").strip()
        subject = str(details[0].get("subject") or "").strip()
        label = _exploration_kind_label(kind)
        return f"{label} {structured_first_summary_line(subject)}".strip()
    if name == "mcp_tool_call":
        invocation = str(structured_payload_input(payload).get("invocation") or "").strip()
        return invocation or structured_payload_title(payload)
    if name in {"view_image", "input_image_output", "view_document", "document_output"}:
        title = structured_payload_title(payload)
        subject = str(structured_payload_input(payload).get("subject") or "").strip()
        return " ".join(structured_first_summary_line(part) for part in (title, subject) if part)
    if entry.layer == "web" or structured_payload_code(payload).startswith("web."):
        query_text = str(structured_payload_input(payload).get("query") or "").strip()
        if query_text:
            return query_text
        output_text = structured_payload_output(payload)
        if output_text:
            return structured_first_summary_line(output_text)
        title = structured_payload_title(payload)
        if title:
            return title
    title = structured_payload_title(payload)
    if title:
        return title
    output_text = structured_payload_output(payload)
    if output_text:
        return structured_first_summary_line(output_text)
    return ""


def _exploration_kind_label(kind: str) -> str:
    normalized = str(kind or "").strip().lower()
    if normalized == "read":
        return "Read"
    if normalized == "search":
        return "Search"
    if normalized == "list":
        return "List"
    if normalized:
        return normalized.capitalize()
    return "Tool"
