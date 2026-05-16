from __future__ import annotations

import re
from typing import Any

from cli.agent_cli.models import PromptAttachment
from cli.agent_cli.ui.transcript_structured_runtime import message_payload, reasoning_payload


def _compact_single_operator_projection(content: str) -> str:
    lines = [str(line or "") for line in str(content or "").splitlines()]
    if len(lines) < 2:
        return str(content or "")
    summary = str(lines[0] or "").strip()
    detail = str(lines[1] or "").strip()
    if not summary or not detail:
        return str(content or "")

    def _subject(line: str) -> tuple[str, str] | None:
        normalized = re.sub(r"^[\s>*+\-•]+", "", line)
        match = re.match(r"^(agent|task)\s+(\S+)", normalized)
        if not match:
            return None
        return str(match.group(1) or "").strip(), str(match.group(2) or "").strip()

    summary_subject = _subject(summary)
    detail_subject = _subject(detail)
    if summary_subject and summary_subject == detail_subject:
        return re.sub(r"^[\s>*+\-•]+", "", summary)
    return str(content or "")


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
    image_count = sum(1 for item in list(attachments or []) if is_image_attachment_fn(item))
    message_text = (
        strip_image_attachment_references_fn(content) if image_count else str(content or "")
    )
    lines: list[str] = [f"  [Image #{index}]" for index in range(1, image_count + 1)]
    if lines and message_text.strip():
        lines.append("")
    if message_text.strip():
        lines.extend(
            format_transcript_block_fn(
                message_text,
                first_prefix=transcript_user_prefix,
                continuation_prefix=transcript_continuation_prefix,
            )
        )
    return transcript_entry_cls(
        kind="user",
        layer="user",
        lines=lines
        or format_transcript_block_fn(
            message_text,
            first_prefix=transcript_user_prefix,
            continuation_prefix=transcript_continuation_prefix,
        ),
        structured=message_payload(
            name="user",
            text=message_text,
            metadata={"image_count": image_count},
        ),
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
    compact_content = _compact_single_operator_projection(content)
    return transcript_entry_cls(
        kind="assistant",
        layer="final",
        lines=format_transcript_block_fn(
            compact_content,
            first_prefix=transcript_message_prefix,
            continuation_prefix=transcript_continuation_prefix,
        ),
        status=str(status or "info"),
        raw_content=compact_content,
        structured=message_payload(
            name="assistant",
            text=compact_content,
            state="error" if str(status or "").strip().lower() == "error" else "completed",
        ),
        render_mode="markdown",
    )


def commentary_message_entry(
    transcript_entry_cls: Any,
    *,
    content: str,
    format_transcript_block_fn: Any,
    transcript_message_prefix: str,
    transcript_continuation_prefix: str,
):
    return transcript_entry_cls(
        kind="assistant",
        layer="commentary",
        lines=format_transcript_block_fn(
            str(content or ""),
            first_prefix=transcript_message_prefix,
            continuation_prefix=transcript_continuation_prefix,
        ),
        raw_content=str(content or ""),
        structured=message_payload(name="commentary", text=str(content or "")),
        render_mode="markdown",
    )


def reasoning_message_entry(
    transcript_entry_cls: Any,
    *,
    content: str,
    format_transcript_block_fn: Any,
    transcript_message_prefix: str,
    transcript_continuation_prefix: str,
):
    text = str(content or "").strip()
    return transcript_entry_cls(
        kind="reasoning",
        layer="reasoning",
        lines=format_transcript_block_fn(
            text,
            first_prefix=transcript_message_prefix,
            continuation_prefix=transcript_continuation_prefix,
        ),
        raw_content=text,
        structured=reasoning_payload(text),
        render_mode="reasoning_markdown",
    )


def is_image_attachment(item: PromptAttachment, *, image_attachment_extensions: set[str]) -> bool:
    extension = str(getattr(item, "extension", "") or "").strip().lower().lstrip(".")
    return extension in image_attachment_extensions


def strip_image_attachment_references(
    content: str, *, inline_attachment_re: re.Pattern[str]
) -> str:
    stripped = inline_attachment_re.sub("", str(content or ""))
    normalized_lines = [re.sub(r"[ \t]{2,}", " ", line).strip() for line in stripped.splitlines()]
    return "\n".join(normalized_lines).strip()
