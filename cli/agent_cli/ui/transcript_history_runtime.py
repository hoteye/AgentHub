from __future__ import annotations

import re
from typing import Any

from cli.agent_cli.models import ActivityEvent, PromptAttachment
from cli.agent_cli.ui import transcript_history_activity_runtime
from cli.agent_cli.ui.transcript_history_message_runtime import (
    assistant_message_entry as _assistant_message_entry,
    commentary_message_entry as _commentary_message_entry,
    is_image_attachment as _is_image_attachment,
    reasoning_message_entry as _reasoning_message_entry,
    strip_image_attachment_references as _strip_image_attachment_references,
    user_message_entry as _user_message_entry,
)
from cli.agent_cli.ui.transcript_history_web_search_runtime import (
    uses_compact_web_search_cell as _uses_compact_web_search_cell,
    web_search_activity_lines as _web_search_activity_lines,
)


def user_message_entry(
    transcript_entry_cls: Any,
    *,
    content: str,
    attachments: list[PromptAttachment] | None,
    is_image_attachment_fn: Any,
    strip_image_attachment_references_fn: Any,
    format_transcript_block_fn: Any,
    transcript_user_prefix: str,
    transcript_continuation_prefix: str,
):
    return _user_message_entry(
        transcript_entry_cls,
        content=content,
        attachments=attachments,
        is_image_attachment_fn=is_image_attachment_fn,
        strip_image_attachment_references_fn=strip_image_attachment_references_fn,
        format_transcript_block_fn=format_transcript_block_fn,
        transcript_user_prefix=transcript_user_prefix,
        transcript_continuation_prefix=transcript_continuation_prefix,
    )


def assistant_message_entry(
    transcript_entry_cls: Any,
    *,
    content: str,
    status: str,
    format_transcript_block_fn: Any,
    transcript_message_prefix: str,
    transcript_continuation_prefix: str,
):
    return _assistant_message_entry(
        transcript_entry_cls,
        content=content,
        status=status,
        format_transcript_block_fn=format_transcript_block_fn,
        transcript_message_prefix=transcript_message_prefix,
        transcript_continuation_prefix=transcript_continuation_prefix,
    )


def commentary_message_entry(
    transcript_entry_cls: Any,
    *,
    content: str,
    format_transcript_block_fn: Any,
    transcript_message_prefix: str,
    transcript_continuation_prefix: str,
):
    return _commentary_message_entry(
        transcript_entry_cls,
        content=content,
        format_transcript_block_fn=format_transcript_block_fn,
        transcript_message_prefix=transcript_message_prefix,
        transcript_continuation_prefix=transcript_continuation_prefix,
    )


def reasoning_message_entry(
    transcript_entry_cls: Any,
    *,
    content: str,
    format_transcript_block_fn: Any,
    transcript_message_prefix: str,
    transcript_continuation_prefix: str,
):
    return _reasoning_message_entry(
        transcript_entry_cls,
        content=content,
        format_transcript_block_fn=format_transcript_block_fn,
        transcript_message_prefix=transcript_message_prefix,
        transcript_continuation_prefix=transcript_continuation_prefix,
    )


def activity_entry(
    transcript_entry_cls: Any,
    event: ActivityEvent,
    *,
    should_skip_activity_entry_fn: Any,
    format_plan_steps_fn: Any,
    format_activity_detail_lines_fn: Any,
    normalized_activity_detail_fn: Any,
    format_web_activity_lines_fn: Any,
    exploration_detail_item_fn: Any,
    format_exploration_activity_lines_fn: Any,
    format_file_activity_lines_fn: Any,
    format_patch_activity_lines_fn: Any,
    format_activity_summary_fn: Any,
    activity_key_fn: Any,
):
    return transcript_history_activity_runtime.activity_entry(
        transcript_entry_cls,
        event,
        should_skip_activity_entry_fn=should_skip_activity_entry_fn,
        format_plan_steps_fn=format_plan_steps_fn,
        format_activity_detail_lines_fn=format_activity_detail_lines_fn,
        normalized_activity_detail_fn=normalized_activity_detail_fn,
        format_web_activity_lines_fn=format_web_activity_lines_fn,
        exploration_detail_item_fn=exploration_detail_item_fn,
        format_exploration_activity_lines_fn=format_exploration_activity_lines_fn,
        format_file_activity_lines_fn=format_file_activity_lines_fn,
        format_patch_activity_lines_fn=format_patch_activity_lines_fn,
        format_activity_summary_fn=format_activity_summary_fn,
        activity_key_fn=activity_key_fn,
        uses_compact_web_search_cell_fn=_uses_compact_web_search_cell,
        web_search_activity_lines_fn=_web_search_activity_lines,
    )


def activity_key(event: ActivityEvent, *, strip_activity_prefix_fn: Any) -> str | None:
    return transcript_history_activity_runtime.activity_key(
        event,
        strip_activity_prefix_fn=strip_activity_prefix_fn,
    )


def should_include_activity_detail(event: ActivityEvent) -> bool:
    return transcript_history_activity_runtime.should_include_activity_detail(event)


def should_skip_activity_entry(event: ActivityEvent) -> bool:
    return transcript_history_activity_runtime.should_skip_activity_entry(event)


def normalized_activity_detail(event: ActivityEvent, *, should_include_activity_detail_fn: Any) -> str:
    return transcript_history_activity_runtime.normalized_activity_detail(
        event,
        should_include_activity_detail_fn=should_include_activity_detail_fn,
    )


def is_image_attachment(item: PromptAttachment, *, image_attachment_extensions: set[str]) -> bool:
    return _is_image_attachment(item, image_attachment_extensions=image_attachment_extensions)


def strip_image_attachment_references(content: str, *, inline_attachment_re: re.Pattern[str]) -> str:
    return _strip_image_attachment_references(content, inline_attachment_re=inline_attachment_re)
