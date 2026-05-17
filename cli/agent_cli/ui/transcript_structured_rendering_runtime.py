from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.cells import cell_len
from rich.style import Style as RichStyle

from cli.agent_cli.ui.theme import ThemeStyles
from cli.agent_cli.ui.transcript_structured_access import (
    payload_code,
    payload_input,
    payload_metadata,
    payload_state,
    payload_summary,
    payload_title,
    string_list,
)
from cli.agent_cli.ui.transcript_structured_rendering_blocks_runtime import (
    file_activity_block_lines,
    web_search_activity_block_lines,
)
from cli.agent_cli.ui.transcript_structured_rendering_tool_runtime import (
    artifact_entry_block_lines,
    command_entry_block_lines,
    command_exploration_entry_block_lines,
    command_metadata_detail_lines,
    duration_label,
    exploration_detail_lines,
    exploration_detail_text,
    mcp_tool_entry_block_lines,
    payload_header,
    todo_body_lines,
    todo_list_entry_block_lines,
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
    rendered_lines = command_entry_block_lines(
        payload,
        width=width,
        block_lines_fn=structured_tool_block_lines,
        metadata_detail_lines_fn=_command_metadata_detail_lines,
        payload_input_fn=payload_input,
        payload_metadata_fn=payload_metadata,
        payload_state_fn=payload_state,
        string_list_fn=string_list,
    )
    return _styled_lines(entry, rendered_lines, styles=styles)


def _command_metadata_detail_lines(metadata: dict[str, Any], *, state: str) -> list[str]:
    return command_metadata_detail_lines(
        metadata,
        state=state,
        duration_label_fn=_duration_label,
    )


def _duration_label(duration_ms: object) -> str:
    return duration_label(duration_ms)


def render_structured_todo_list_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    rendered_lines = todo_list_entry_block_lines(
        payload,
        width=width,
        wrap_text_fn=wrap_prefixed_text,
        todo_body_lines_fn=_wrap_todo_body_line,
        payload_input_fn=payload_input,
        payload_metadata_fn=payload_metadata,
    )
    return _styled_lines(entry, rendered_lines, styles=styles)


def render_structured_command_exploration_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    rendered_lines = command_exploration_entry_block_lines(
        payload,
        width=width,
        block_lines_fn=structured_tool_block_lines,
        payload_header_fn=_payload_header,
        exploration_detail_text_fn=_exploration_detail_text,
        payload_input_fn=payload_input,
    )
    return _styled_lines(entry, rendered_lines, styles=styles)


def render_structured_mcp_tool_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    rendered_lines = mcp_tool_entry_block_lines(
        payload,
        width=width,
        block_lines_fn=structured_tool_block_lines,
        cell_len_fn=cell_len,
        payload_input_fn=payload_input,
        payload_metadata_fn=payload_metadata,
        payload_state_fn=payload_state,
    )
    return _styled_lines(entry, rendered_lines, styles=styles)


def render_structured_artifact_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    lines = artifact_entry_block_lines(
        payload,
        width=width,
        block_lines_fn=structured_tool_block_lines,
        payload_input_fn=payload_input,
        payload_metadata_fn=payload_metadata,
        payload_summary_fn=payload_summary,
    )
    return _styled_lines(entry, lines, styles=styles)


def render_structured_web_search_activity_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    header = _payload_header(payload, default="Web search")
    lines = web_search_activity_block_lines(
        payload,
        width=width,
        header=header,
        backend_header=header,
        block_lines_fn=structured_tool_block_lines,
    )
    return _styled_lines(entry, lines, styles=styles)


def render_structured_file_activity_entry_lines(
    entry: TranscriptEntry,
    payload: dict[str, Any],
    *,
    width: int,
    styles: ThemeStyles,
) -> list[RenderedLine]:
    lines = file_activity_block_lines(
        payload,
        width=width,
        header=_payload_header(payload, default="File activity"),
        block_lines_fn=structured_tool_block_lines,
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
    return todo_body_lines(
        text,
        width=width,
        branch_prefix=branch_prefix,
        wrap_text_fn=wrap_prefixed_text,
    )


def _wrap_exploration_detail(
    detail: dict[str, Any], *, width: int, branch_prefix: str
) -> list[str]:
    return exploration_detail_lines(
        detail,
        width=width,
        branch_prefix=branch_prefix,
        exploration_detail_text_fn=_exploration_detail_text,
        wrap_text_fn=wrap_prefixed_text,
    )


def _exploration_detail_text(detail: dict[str, Any]) -> str:
    return exploration_detail_text(detail)


def _payload_header(payload: dict[str, Any], *, default: str) -> str:
    return payload_header(payload, default=default, payload_title_fn=payload_title)
