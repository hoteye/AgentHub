from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.cells import cell_len
from rich.style import Style as RichStyle

from cli.agent_cli.ui.theme import ThemeStyles
from cli.agent_cli.ui.transcript_structured_access import (
    payload_code,
    payload_input,
    payload_metadata,
    payload_output,
    payload_state,
    payload_summary,
    payload_title,
    string_list,
)
from cli.agent_cli.ui.transcript_structured_visual_blocks import structured_tool_block_lines
from cli.agent_cli.ui.transcript_visual_rendering_helpers import (
    plain_line_styles,
    prefixed_visual_lines,
    wrap_prefixed_text,
)

if TYPE_CHECKING:
    from cli.agent_cli.ui.transcript_history import TranscriptEntry


RenderedLine = tuple[str, list[tuple[int, int, RichStyle]]]


class ToolTranscriptRenderer:
    tool_names: frozenset[str] = frozenset()

    def can_render(self, entry: TranscriptEntry, payload: dict[str, Any]) -> bool:
        del entry
        if str(payload.get("type") or "").strip() != "tool":
            return False
        return str(payload.get("name") or "").strip() in self.tool_names

    def render_inline(
        self,
        entry: TranscriptEntry,
        payload: dict[str, Any],
        *,
        width: int,
        styles: ThemeStyles,
    ) -> list[RenderedLine]:
        raise NotImplementedError

    def render_block(
        self,
        entry: TranscriptEntry,
        payload: dict[str, Any],
        *,
        width: int,
        styles: ThemeStyles,
    ) -> list[RenderedLine]:
        return self.render_inline(entry, payload, width=width, styles=styles)


class CommandExplorationRenderer(ToolTranscriptRenderer):
    tool_names = frozenset({"command_exploration"})

    def render_inline(
        self,
        entry: TranscriptEntry,
        payload: dict[str, Any],
        *,
        width: int,
        styles: ThemeStyles,
    ) -> list[RenderedLine]:
        return render_structured_command_exploration_entry_lines(
            entry, payload, width=width, styles=styles
        )


class ShellToolRenderer(ToolTranscriptRenderer):
    tool_names = frozenset({"command_execution"})

    def render_inline(
        self,
        entry: TranscriptEntry,
        payload: dict[str, Any],
        *,
        width: int,
        styles: ThemeStyles,
    ) -> list[RenderedLine]:
        return render_structured_command_entry_lines(entry, payload, width=width, styles=styles)


class TodoToolRenderer(ToolTranscriptRenderer):
    tool_names = frozenset({"todo_list"})

    def render_inline(
        self,
        entry: TranscriptEntry,
        payload: dict[str, Any],
        *,
        width: int,
        styles: ThemeStyles,
    ) -> list[RenderedLine]:
        return render_structured_todo_list_entry_lines(entry, payload, width=width, styles=styles)


class GenericMcpToolRenderer(ToolTranscriptRenderer):
    tool_names = frozenset({"mcp_tool_call"})

    def render_inline(
        self,
        entry: TranscriptEntry,
        payload: dict[str, Any],
        *,
        width: int,
        styles: ThemeStyles,
    ) -> list[RenderedLine]:
        return render_structured_mcp_tool_entry_lines(entry, payload, width=width, styles=styles)


class ArtifactToolRenderer(ToolTranscriptRenderer):
    tool_names = frozenset({"document_output", "input_image_output", "view_document", "view_image"})

    def render_inline(
        self,
        entry: TranscriptEntry,
        payload: dict[str, Any],
        *,
        width: int,
        styles: ThemeStyles,
    ) -> list[RenderedLine]:
        return render_structured_artifact_entry_lines(entry, payload, width=width, styles=styles)


class ActivityTranscriptRenderer:
    activity_names: frozenset[str] = frozenset()

    def can_render(self, entry: TranscriptEntry, payload: dict[str, Any]) -> bool:
        del entry
        if str(payload.get("type") or "").strip() != "activity":
            return False
        return payload_code(payload) in self.activity_names

    def render_inline(
        self,
        entry: TranscriptEntry,
        payload: dict[str, Any],
        *,
        width: int,
        styles: ThemeStyles,
    ) -> list[RenderedLine]:
        raise NotImplementedError


class WebSearchActivityRenderer(ActivityTranscriptRenderer):
    activity_names = frozenset({"web.search"})

    def render_inline(
        self,
        entry: TranscriptEntry,
        payload: dict[str, Any],
        *,
        width: int,
        styles: ThemeStyles,
    ) -> list[RenderedLine]:
        return render_structured_web_search_activity_entry_lines(
            entry, payload, width=width, styles=styles
        )


class FileActivityRenderer(ActivityTranscriptRenderer):
    activity_names = frozenset({"dir.list", "dir.search", "file.list", "file.search", "file.read"})

    def render_inline(
        self,
        entry: TranscriptEntry,
        payload: dict[str, Any],
        *,
        width: int,
        styles: ThemeStyles,
    ) -> list[RenderedLine]:
        return render_structured_file_activity_entry_lines(
            entry, payload, width=width, styles=styles
        )


STRUCTURED_TOOL_RENDERERS: tuple[ToolTranscriptRenderer, ...] = (
    CommandExplorationRenderer(),
    ShellToolRenderer(),
    TodoToolRenderer(),
    GenericMcpToolRenderer(),
    ArtifactToolRenderer(),
)

STRUCTURED_ACTIVITY_RENDERERS: tuple[ActivityTranscriptRenderer, ...] = (
    WebSearchActivityRenderer(),
    FileActivityRenderer(),
)


def structured_renderer_tool_names() -> tuple[str, ...]:
    names: set[str] = set()
    for renderer in STRUCTURED_TOOL_RENDERERS:
        names.update(renderer.tool_names)
    return tuple(sorted(names))


def structured_visual_lines_for_entry(
    entry: TranscriptEntry,
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine] | None:
    payload = entry.structured
    if not isinstance(payload, dict):
        return None
    for renderer in STRUCTURED_TOOL_RENDERERS:
        if renderer.can_render(entry, payload):
            return renderer.render_inline(entry, payload, width=width, styles=styles)
    for renderer in STRUCTURED_ACTIVITY_RENDERERS:
        if renderer.can_render(entry, payload):
            return renderer.render_inline(entry, payload, width=width, styles=styles)
    return None


def render_structured_command_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    input_payload = payload_input(payload)
    metadata = payload_metadata(payload)
    command_lines = string_list(input_payload.get("command_lines"))
    command_text = str(
        input_payload.get("display_command") or input_payload.get("command") or ""
    ).strip()
    if not command_lines:
        command_lines = command_text.splitlines() or [command_text or "command"]
    output_lines = string_list(metadata.get("output_lines"))
    if not output_lines:
        output_text = str(payload.get("output") or "")
        output_lines = [line.rstrip() for line in output_text.splitlines() if line.strip()]

    state = payload_state(payload)
    completed = state in {"completed", "error"}
    header_word = "Ran" if completed else "Running"
    header_command = command_lines[0] if command_lines else command_text
    metadata_lines = [*command_lines[1:], *_command_metadata_detail_lines(metadata, state=state)]
    rendered_lines = structured_tool_block_lines(
        f"{header_word} {str(header_command or 'command').strip()}",
        width=width,
        metadata=metadata_lines,
        details=output_lines,
        empty_detail="(no output)" if completed else "",
    )
    return _styled_lines(entry, rendered_lines, styles=styles)


def _command_metadata_detail_lines(metadata: dict[str, Any], *, state: str) -> list[str]:
    details: list[str] = []
    cwd = str(metadata.get("cwd") or "").strip()
    if cwd:
        details.append(f"cwd: {cwd}")
    exit_code = metadata.get("exit_code")
    if exit_code not in {None, ""} and state in {"completed", "error"}:
        details.append(f"exit: {exit_code}")
    duration_label = _duration_label(metadata.get("duration_ms"))
    if duration_label:
        details.append(f"duration: {duration_label}")
    process_id = str(metadata.get("process_id") or "").strip()
    if process_id and state == "running":
        details.append(f"session: {process_id}")
    output_line_count = metadata.get("output_line_count")
    if bool(metadata.get("output_truncated")) and output_line_count not in {None, ""}:
        details.append(f"output: {output_line_count} lines, preview shown")
    return details


def _duration_label(duration_ms: object) -> str:
    try:
        value = int(duration_ms)
    except (TypeError, ValueError):
        return ""
    if value < 0:
        return ""
    if value < 1000:
        return f"{value}ms"
    return f"{value / 1000:.2f}s"


def render_structured_todo_list_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    input_payload = payload_input(payload)
    metadata = payload_metadata(payload)
    todos = [item for item in input_payload.get("items") or [] if isinstance(item, dict)]
    plan_style = str(metadata.get("source") or "").strip() == "plan_activity"
    rendered_lines = wrap_prefixed_text(
        str(payload.get("title") or "Todo List"),
        first_prefix="• ",
        continuation_prefix="  ",
        width=width,
    )
    if todos:
        for index, todo in enumerate(todos):
            marker = "" if plan_style else ("✔ " if bool(todo.get("completed")) else "□ ")
            branch_prefix = "  └ " if index == 0 else "    "
            rendered_lines.extend(
                _wrap_todo_body_line(
                    f"{marker}{str(todo.get('text') or '').strip()}",
                    width=width,
                    branch_prefix=branch_prefix,
                )
            )
    else:
        rendered_lines.extend(
            _wrap_todo_body_line(
                "(no steps provided)",
                width=width,
                branch_prefix="  └ ",
            )
        )
    return _styled_lines(entry, rendered_lines, styles=styles)


def render_structured_command_exploration_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    input_payload = payload_input(payload)
    details = [item for item in input_payload.get("details") or [] if isinstance(item, dict)]
    rendered_lines = structured_tool_block_lines(
        _payload_header(payload, default="Explored"),
        width=width,
        details=[_exploration_detail_text(detail) for detail in details],
    )
    return _styled_lines(entry, rendered_lines, styles=styles)


def render_structured_mcp_tool_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    input_payload = payload_input(payload)
    metadata = payload_metadata(payload)
    invocation = str(input_payload.get("invocation") or "").strip()
    if not invocation:
        server = str(metadata.get("server") or "local").strip() or "local"
        tool_name = str(metadata.get("tool_name") or "tool").strip() or "tool"
        invocation = f"{server}.{tool_name}"
    state = payload_state(payload)
    completed = state in {"completed", "error"}
    header_word = "Called" if completed else "Calling"
    detail = str(payload.get("output") or "").strip()
    header = f"{header_word} {invocation}".rstrip()
    inline_invocation = cell_len(f"• {header}") <= max(1, int(width))
    metadata_lines = [] if inline_invocation else [invocation or "tool"]
    if not inline_invocation:
        header = header_word
    if detail:
        detail_lines = [detail]
    elif completed and state == "error":
        error_text = str(payload_metadata(payload).get("error") or "").strip()
        detail_lines = [f"Error: {error_text}"] if error_text else []
    else:
        detail_lines = []
    rendered_lines = structured_tool_block_lines(
        header,
        width=width,
        metadata=metadata_lines,
        details=detail_lines,
    )
    return _styled_lines(entry, rendered_lines, styles=styles)


def render_structured_artifact_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    input_payload = payload_input(payload)
    metadata = payload_metadata(payload)
    title = payload_summary(payload) or str(payload.get("title") or "").strip() or "Artifact"
    subject = (
        str(input_payload.get("subject") or "").strip()
        or str(metadata.get("subject") or "").strip()
    )
    state = str(metadata.get("state") or payload.get("state") or "").strip()
    lines = structured_tool_block_lines(
        title,
        width=width,
        metadata=[f"state: {state}"] if state else [],
        details=[subject] if subject and subject not in title else [],
    )
    return _styled_lines(entry, lines, styles=styles)


def render_structured_web_search_activity_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    lines = structured_tool_block_lines(
        _payload_header(payload, default="Web search"),
        width=width,
        metadata=_web_search_metadata_lines(payload),
        details=_web_search_detail_lines(payload),
    )
    return _styled_lines(entry, lines, styles=styles)


def render_structured_file_activity_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    lines = structured_tool_block_lines(
        _payload_header(payload, default="File activity"),
        width=width,
        metadata=_file_activity_metadata_lines(payload),
        details=_file_activity_detail_lines(payload),
    )
    return _styled_lines(entry, lines, styles=styles)


def _styled_lines(
    entry: TranscriptEntry,
    rendered_lines: list[str],
    *,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    visual_lines = prefixed_visual_lines(entry, rendered_lines)
    return [
        (line_text, plain_line_styles(entry, line_index, line_text, styles=styles))
        for line_index, line_text in enumerate(visual_lines)
    ]


def _wrap_todo_body_line(text: str, *, width: int, branch_prefix: str) -> list[str]:
    body_text = str(text or "")
    for marker in ("✔ ", "□ "):
        if body_text.startswith(marker):
            return wrap_prefixed_text(
                body_text[len(marker) :],
                first_prefix=f"{branch_prefix}{marker}",
                continuation_prefix=" " * (len(branch_prefix) + len(marker)),
                width=width,
            )
    continuation_prefix = " " * len(branch_prefix)
    return wrap_prefixed_text(
        body_text,
        first_prefix=branch_prefix,
        continuation_prefix=continuation_prefix,
        width=width,
    )


def _wrap_exploration_detail(
    detail: dict[str, Any], *, width: int, branch_prefix: str
) -> list[str]:
    return wrap_prefixed_text(
        _exploration_detail_text(detail) or "(unknown)",
        first_prefix=branch_prefix,
        continuation_prefix=" " * len(branch_prefix),
        width=width,
    )


def _exploration_detail_text(detail: dict[str, Any]) -> str:
    kind = str(detail.get("kind") or "").strip()
    subject = str(detail.get("subject") or "").strip()
    if kind == "list":
        return f"List {subject or '.'}".strip()
    if kind == "search":
        return f"Search {subject}".strip()
    if kind == "read":
        return f"Read {subject}".strip()
    return subject


def _payload_header(payload: dict[str, Any], *, default: str) -> str:
    header = payload_title(payload) or str(payload.get("title") or "").strip()
    if not header:
        header = str(default or "").strip()
    for prefix in ("• ", "✗ ", "⌕ ", "◆ ", "▸ ", "□ ", "◦ "):
        if header.startswith(prefix):
            return header[len(prefix) :].strip() or default
    return header or default


def _web_search_metadata_lines(payload: dict[str, Any]) -> list[str]:
    input_payload = payload_input(payload)
    output_text = payload_output(payload)
    lines: list[str] = []
    outcome = _web_search_outcome(payload)
    backend = _web_search_backend(payload)
    count_text = _first_text(input_payload.get("count"), _detail_lookup(output_text, "count"))
    if outcome:
        lines.append(f"state: {outcome}")
    if backend:
        lines.append(f"backend: {backend}")
    if count_text:
        lines.append(f"count: {count_text}")
    return lines


def _web_search_detail_lines(payload: dict[str, Any]) -> list[str]:
    input_payload = payload_input(payload)
    output_text = payload_output(payload)
    query_text = _first_text(
        input_payload.get("query"),
        _detail_lookup(output_text, "query"),
        _clean_summary_query(payload_summary(payload)),
    )
    details: list[str] = []
    if query_text:
        details.append(query_text)
    elif count_text := _first_text(
        input_payload.get("count"), _detail_lookup(output_text, "count")
    ):
        details.append(_count_label(count_text, singular="result", plural="results"))
    details.extend(_web_search_reason_lines(output_text))
    return details


def _web_search_outcome(payload: dict[str, Any]) -> str:
    input_payload = payload_input(payload)
    explicit = _first_text(
        input_payload.get("web_search_outcome"),
        input_payload.get("search_phase"),
        _detail_lookup(payload_output(payload), "state"),
    ).lower()
    if explicit:
        return explicit
    state = payload_state(payload)
    has_backend_or_count = bool(
        _web_search_backend(payload)
        or _first_text(input_payload.get("count"), _detail_lookup(payload_output(payload), "count"))
    )
    if state == "running" and has_backend_or_count:
        return "search_dispatched"
    if state == "completed" and has_backend_or_count:
        return "search_results_received"
    if state == "error" and has_backend_or_count:
        return "search_failed"
    return ""


def _web_search_backend(payload: dict[str, Any]) -> str:
    input_payload = payload_input(payload)
    metadata = payload_metadata(payload)
    backend = _first_text(input_payload.get("backend"), metadata.get("backend")).lower()
    if backend in {"native", "local"}:
        return backend
    if bool(input_payload.get("provider_native")):
        return "native"
    title = _payload_header(payload, default="").lower()
    if title.startswith("native web search"):
        return "native"
    if title.startswith("local web search"):
        return "local"
    return ""


def _web_search_reason_lines(output_text: str) -> list[str]:
    reasons: list[str] = []
    for line in _detail_lines(output_text):
        lowered = line.lower()
        if lowered.startswith(("query=", "count=", "state=", "backend=")):
            continue
        if _looks_like_ranked_web_result(line):
            continue
        if line.startswith("reason="):
            reasons.append(f"reason: {line.partition('=')[2].strip()}")
        elif "=" in line:
            reasons.append(line.replace("=", ": ", 1))
        else:
            reasons.append(f"reason: {line}")
    return reasons


def _file_activity_metadata_lines(payload: dict[str, Any]) -> list[str]:
    input_payload = payload_input(payload)
    output_text = payload_output(payload)
    lines: list[str] = []
    count_text = _first_text(input_payload.get("count"), _detail_lookup(output_text, "count"))
    if count_text:
        lines.append(f"count: {count_text}")
    if truncated := _first_text(
        input_payload.get("truncated"), _detail_lookup(output_text, "truncated")
    ):
        lines.append(f"truncated: {truncated}")
    return lines


def _file_activity_detail_lines(payload: dict[str, Any]) -> list[str]:
    input_payload = payload_input(payload)
    output_text = payload_output(payload)
    code = payload_code(payload)
    if code in {"dir.search", "file.search"}:
        subject = _search_subject(
            _first_text(
                input_payload.get("query"),
                input_payload.get("pattern"),
                _detail_lookup(output_text, "query"),
                _detail_lookup(output_text, "pattern"),
            ),
            _first_text(
                input_payload.get("path"),
                input_payload.get("dir_path"),
                _detail_lookup(output_text, "path"),
                _detail_lookup(output_text, "dir_path"),
            ),
        )
        return [subject] if subject else _non_metadata_detail_lines(output_text)
    if code in {"dir.list", "file.list"}:
        subject = _first_text(
            input_payload.get("path"),
            input_payload.get("dir_path"),
            _detail_lookup(output_text, "path"),
            _detail_lookup(output_text, "dir_path"),
            payload_summary(payload),
        )
        return [subject] if subject else _non_metadata_detail_lines(output_text)
    if code == "file.read":
        subject = _first_text(
            input_payload.get("file_path"),
            input_payload.get("path"),
            _detail_lookup(output_text, "file_path"),
            _detail_lookup(output_text, "path"),
            _first_detail_segment(output_text),
            payload_summary(payload),
        )
        return [subject] if subject else _non_metadata_detail_lines(output_text)
    return _non_metadata_detail_lines(output_text)


def _detail_lookup(output_text: str, *keys: str) -> str:
    key_set = {str(key).strip().lower() for key in keys if str(key).strip()}
    for line in _detail_lines(output_text):
        key, separator, value = line.partition("=")
        if separator and key.strip().lower() in key_set and value.strip():
            return value.strip()
    return ""


def _detail_lines(output_text: str) -> list[str]:
    return [line.strip() for line in str(output_text or "").splitlines() if line.strip()]


def _non_metadata_detail_lines(output_text: str) -> list[str]:
    lines: list[str] = []
    for line in _detail_lines(output_text):
        key = line.partition("=")[0].strip().lower()
        if key in {"count", "query", "pattern", "path", "dir_path", "file_path", "truncated"}:
            continue
        lines.append(line)
    return lines


def _first_detail_segment(output_text: str) -> str:
    for line in _detail_lines(output_text):
        first_segment = line.split(" | ", maxsplit=1)[0].strip()
        if first_segment and "=" not in first_segment:
            return first_segment
    return ""


def _first_text(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _clean_summary_query(summary: str) -> str:
    text = str(summary or "").strip()
    if text.lower().startswith(("query=", "pattern=")):
        return text.partition("=")[2].strip()
    return text


def _search_subject(query: str, path: str) -> str:
    if query and path:
        return f"{query} in {path}"
    return query or path


def _count_label(count_text: str, *, singular: str, plural: str) -> str:
    label = singular if str(count_text).strip() == "1" else plural
    return f"{count_text} {label}"


def _looks_like_ranked_web_result(line: str) -> bool:
    stripped = str(line or "").strip()
    index, separator, _rest = stripped.partition(". ")
    return bool(separator and index.isdigit())
