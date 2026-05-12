from __future__ import annotations

from dataclasses import dataclass
import re

from rich.style import Style as RichStyle

from cli.agent_cli.models import ActivityEvent, PromptAttachment
from cli.agent_cli.ui import transcript_history_runtime
from cli.agent_cli.ui.theme import (
    COMPLETION_TIME_STYLE as THEME_COMPLETION_TIME_STYLE,
    ACCENT_CYAN,
    ACCENT_CYAN_SOFT,
    ERROR,
    ERROR_SOFT,
    ACCENT_BLOCKQUOTE,
    ACCENT_CODE,
    ACCENT_LINK,
    ACCENT_ORDERED_MARKER,
    SYNTAX_BUILTIN,
    SYNTAX_COMMENT,
    SYNTAX_KEYWORD,
    SYNTAX_NAME,
    SYNTAX_NUMBER,
    SYNTAX_OPERATOR,
    SYNTAX_STRING,
    TEXT_DIM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TRANSCRIPT_CONTINUATION_PREFIX,
    TRANSCRIPT_MESSAGE_PREFIX,
    TRANSCRIPT_USER_PREFIX,
    USER_SURFACE_BG,
)
from cli.agent_cli.ui.transcript_formatting import (
    exploration_detail_item,
    format_exploration_activity_lines,
    format_activity_detail_lines,
    format_activity_summary,
    format_file_activity_lines,
    format_patch_activity_lines,
    format_plan_steps,
    format_transcript_block,
    format_web_activity_lines,
    strip_activity_prefix,
)
from cli.agent_cli.ui import transcript_visual_rendering as _transcript_visual_rendering


@dataclass(slots=True)
class TranscriptEntry:
    kind: str
    layer: str
    lines: list[str]
    status: str = "info"
    activity_key: str | None = None
    exploration_details: list[tuple[str, str]] | None = None
    expanded_lines: list[str] | None = None
    expanded: bool = False
    raw_content: str | None = None
    render_mode: str = "plain"
    entry_id: str = ""
    created_at: float = 0.0
    group_key: str | None = None
    search_text: str = ""
    streaming: bool = False
    child_entry_ids: tuple[str, ...] = ()


USER_TEXT_STYLE = RichStyle(color=TEXT_PRIMARY, bgcolor=USER_SURFACE_BG)
USER_PREFIX_STYLE = RichStyle(color=TEXT_MUTED, bgcolor=USER_SURFACE_BG, bold=True, dim=True)
USER_IMAGE_STYLE = RichStyle(color=ACCENT_CYAN, bgcolor=USER_SURFACE_BG)
SYSTEM_TEXT_STYLE = RichStyle(color=TEXT_MUTED)
COMMENTARY_TEXT_STYLE = RichStyle(color=TEXT_SECONDARY)
COMMENTARY_PREFIX_STYLE = RichStyle(color=TEXT_MUTED, bold=True, dim=True)
FINAL_TEXT_STYLE = RichStyle(color=TEXT_PRIMARY)
FINAL_PREFIX_STYLE = RichStyle(color=TEXT_MUTED, bold=True, dim=True)
REASONING_TEXT_STYLE = RichStyle(color=TEXT_MUTED, dim=True, italic=True)
REASONING_PREFIX_STYLE = RichStyle(color=TEXT_DIM, dim=True)
MARKDOWN_H1_STYLE = RichStyle(bold=True, underline=True)
MARKDOWN_H2_STYLE = RichStyle(bold=True)
MARKDOWN_H3_STYLE = RichStyle(bold=True, italic=True)
MARKDOWN_H4_STYLE = RichStyle(italic=True)
MARKDOWN_H5_STYLE = RichStyle(italic=True)
MARKDOWN_H6_STYLE = RichStyle(italic=True)
MARKDOWN_EMPHASIS_STYLE = RichStyle(italic=True)
MARKDOWN_STRONG_STYLE = RichStyle(bold=True)
MARKDOWN_CODE_STYLE = RichStyle(color=ACCENT_CODE)
MARKDOWN_LINK_STYLE = RichStyle(color=ACCENT_LINK, underline=True)
MARKDOWN_BLOCKQUOTE_STYLE = RichStyle(color=ACCENT_BLOCKQUOTE)
MARKDOWN_ORDERED_LIST_MARKER_STYLE = RichStyle(color=ACCENT_ORDERED_MARKER)
MARKDOWN_SYNTAX_COMMENT_STYLE = RichStyle(color=SYNTAX_COMMENT, italic=True)
MARKDOWN_SYNTAX_KEYWORD_STYLE = RichStyle(color=SYNTAX_KEYWORD)
MARKDOWN_SYNTAX_STRING_STYLE = RichStyle(color=SYNTAX_STRING)
MARKDOWN_SYNTAX_NUMBER_STYLE = RichStyle(color=SYNTAX_NUMBER)
MARKDOWN_SYNTAX_OPERATOR_STYLE = RichStyle(color=SYNTAX_OPERATOR)
MARKDOWN_SYNTAX_NAME_STYLE = RichStyle(color=SYNTAX_NAME)
MARKDOWN_SYNTAX_BUILTIN_STYLE = RichStyle(color=SYNTAX_BUILTIN)
ACTIVITY_TEXT_STYLE = RichStyle(color=TEXT_SECONDARY)
ACTIVITY_PREFIX_STYLE = RichStyle(color=TEXT_MUTED, bold=True, dim=True)
ACTIVITY_DETAIL_STYLE = RichStyle(color=TEXT_MUTED)
WEB_TEXT_STYLE = RichStyle(color=ACCENT_CYAN_SOFT)
ERROR_TEXT_STYLE = RichStyle(color=ERROR, bold=True)
ERROR_DETAIL_STYLE = RichStyle(color=ERROR_SOFT)
SEPARATOR_TEXT_STYLE = RichStyle(color=TEXT_DIM, dim=True)
TREE_PREFIX_STYLE = RichStyle(color=TEXT_DIM)
COMPLETION_TIME_STYLE = THEME_COMPLETION_TIME_STYLE
_INLINE_ATTACHMENT_RE = re.compile(r"(?<!\S)@(?:\"[^\"]+\"|'[^']+'|\S+)")
_IMAGE_ATTACHMENT_EXTENSIONS = {
    "apng",
    "avif",
    "bmp",
    "gif",
    "heic",
    "heif",
    "jpeg",
    "jpg",
    "png",
    "svg",
    "tif",
    "tiff",
    "webp",
}



def blank_entry() -> TranscriptEntry:
    return TranscriptEntry(kind="blank", layer="layout", lines=[""])


def system_notice_entry(content: str) -> TranscriptEntry:
    return TranscriptEntry(kind="system", layer="system", lines=[str(content or "")])


def final_separator_entry(label: str = "") -> TranscriptEntry:
    text = str(label or "").strip()
    plain = _separator_line(64, label=text)
    return TranscriptEntry(
        kind="separator",
        layer="separator",
        lines=[plain],
        raw_content=text,
        render_mode="separator",
    )


def user_message_entry(content: str, *, attachments: list[PromptAttachment] | None = None) -> TranscriptEntry:
    return transcript_history_runtime.user_message_entry(
        TranscriptEntry,
        content=content,
        attachments=attachments,
        is_image_attachment_fn=_is_image_attachment,
        strip_image_attachment_references_fn=_strip_image_attachment_references,
        format_transcript_block_fn=format_transcript_block,
        transcript_user_prefix=TRANSCRIPT_USER_PREFIX,
        transcript_continuation_prefix=TRANSCRIPT_CONTINUATION_PREFIX,
    )


def assistant_message_entry(content: str, *, status: str = "info") -> TranscriptEntry:
    return transcript_history_runtime.assistant_message_entry(
        TranscriptEntry,
        content=content,
        status=status,
        format_transcript_block_fn=format_transcript_block,
        transcript_message_prefix=TRANSCRIPT_MESSAGE_PREFIX,
        transcript_continuation_prefix=TRANSCRIPT_CONTINUATION_PREFIX,
    )


def commentary_message_entry(content: str) -> TranscriptEntry:
    return transcript_history_runtime.commentary_message_entry(
        TranscriptEntry,
        content=content,
        format_transcript_block_fn=format_transcript_block,
        transcript_message_prefix=TRANSCRIPT_MESSAGE_PREFIX,
        transcript_continuation_prefix=TRANSCRIPT_CONTINUATION_PREFIX,
    )


def reasoning_message_entry(content: str) -> TranscriptEntry:
    return transcript_history_runtime.reasoning_message_entry(
        TranscriptEntry,
        content=content,
        format_transcript_block_fn=format_transcript_block,
        transcript_message_prefix=TRANSCRIPT_MESSAGE_PREFIX,
        transcript_continuation_prefix=TRANSCRIPT_CONTINUATION_PREFIX,
    )


def activity_entry(event: ActivityEvent) -> TranscriptEntry | None:
    return transcript_history_runtime.activity_entry(
        TranscriptEntry,
        event,
        should_skip_activity_entry_fn=should_skip_activity_entry,
        format_plan_steps_fn=format_plan_steps,
        format_activity_detail_lines_fn=format_activity_detail_lines,
        normalized_activity_detail_fn=normalized_activity_detail,
        format_web_activity_lines_fn=format_web_activity_lines,
        exploration_detail_item_fn=exploration_detail_item,
        format_exploration_activity_lines_fn=format_exploration_activity_lines,
        format_file_activity_lines_fn=format_file_activity_lines,
        format_patch_activity_lines_fn=format_patch_activity_lines,
        format_activity_summary_fn=format_activity_summary,
        activity_key_fn=activity_key,
    )


def activity_key(event: ActivityEvent) -> str | None:
    return transcript_history_runtime.activity_key(event, strip_activity_prefix_fn=strip_activity_prefix)


def should_include_activity_detail(event: ActivityEvent) -> bool:
    return transcript_history_runtime.should_include_activity_detail(event)


def should_skip_activity_entry(event: ActivityEvent) -> bool:
    return transcript_history_runtime.should_skip_activity_entry(event)


def normalized_activity_detail(event: ActivityEvent) -> str:
    return transcript_history_runtime.normalized_activity_detail(
        event,
        should_include_activity_detail_fn=should_include_activity_detail,
    )


def _is_image_attachment(item: PromptAttachment) -> bool:
    return transcript_history_runtime.is_image_attachment(
        item,
        image_attachment_extensions=_IMAGE_ATTACHMENT_EXTENSIONS,
    )


def _strip_image_attachment_references(content: str) -> str:
    return transcript_history_runtime.strip_image_attachment_references(
        content,
        inline_attachment_re=_INLINE_ATTACHMENT_RE,
    )
RenderedTranscript = _transcript_visual_rendering.RenderedTranscript
render_transcript_entries = _transcript_visual_rendering.render_transcript_entries
render_transcript_visual_entries = _transcript_visual_rendering.render_transcript_visual_entries
_separator_line = _transcript_visual_rendering._separator_line
