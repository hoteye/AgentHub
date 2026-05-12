from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.cells import cell_len
from rich.text import Text


def prompt_prefix(composer: Any, width: int) -> str:
    base = str(getattr(composer, "PROMPT_PREFIX", "") or "")
    return base if width >= len(base) else "›"


def continuation_prefix(composer: Any, width: int) -> str:
    return " " * len(prompt_prefix(composer, width))


def display_width(composer: Any, value: str) -> int:
    if not value:
        return 0
    cursor_token = str(getattr(composer, "CURSOR_TOKEN", "") or "")
    if value == cursor_token:
        cursor_glyph = str(getattr(composer, "CURSOR_GLYPH", "") or "")
        return max(1, cell_len(cursor_glyph))
    return cell_len(str(value).replace(cursor_token, ""))


def line_segments(composer: Any, raw_line: str) -> list[str]:
    if raw_line == "":
        return [""]
    cursor_token = str(getattr(composer, "CURSOR_TOKEN", "") or "")
    segments: list[str] = []
    cursor_pending = False
    for char in raw_line:
        if char == cursor_token:
            cursor_pending = True
            continue
        if cursor_pending:
            segments.append(cursor_token + char)
            cursor_pending = False
        else:
            segments.append(char)
    if cursor_pending:
        segments.append(cursor_token)
    return segments or [""]


def visual_lines(
    composer: Any,
    text: str,
    cursor_pos: int,
    width: int,
    *,
    include_cursor: bool = True,
) -> list[str]:
    prefix = prompt_prefix(composer, width)
    content_width = max(1, width - cell_len(prefix))
    source_text = text
    cursor_token = str(getattr(composer, "CURSOR_TOKEN", "") or "")
    if include_cursor:
        cursor_index = max(0, min(len(text), cursor_pos))
        source_text = text[:cursor_index] + cursor_token + text[cursor_index:]
    logical_lines = source_text.split("\n")
    visual: list[str] = []

    for raw_line in logical_lines:
        if raw_line == "":
            visual.append("")
            continue
        segments = line_segments(composer, raw_line)
        if not segments:
            visual.append("")
            continue
        current_segments: list[str] = []
        current_width = 0
        for segment in segments:
            segment_width = max(0, display_width(composer, segment))
            if current_segments and current_width + segment_width > content_width:
                visual.append("".join(current_segments))
                current_segments = [segment]
                current_width = segment_width
                continue
            current_segments.append(segment)
            current_width += segment_width
        visual.append("".join(current_segments))

    return visual or [cursor_token if include_cursor else ""]


def is_image_attachment_reference(composer: Any, token: str) -> bool:
    text = str(token or "").strip()
    if text.startswith("@"):
        text = text[1:].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    suffix = Path(text.replace("\\", "/")).suffix.lower().lstrip(".")
    image_extensions = set(getattr(composer, "IMAGE_ATTACHMENT_EXTENSIONS", set()) or set())
    return suffix in image_extensions


def display_text_and_cursor(composer: Any, text: str, cursor_pos: int) -> tuple[str, int]:
    source = str(text or "")
    cursor = max(0, min(int(cursor_pos), len(source)))
    parts: list[str] = []
    display_cursor = 0
    raw_index = 0
    image_index = 0
    attachment_reference_re = getattr(composer, "ATTACHMENT_REFERENCE_RE")

    for match in attachment_reference_re.finditer(source):
        start, end = match.span()
        before = source[raw_index:start]
        parts.append(before)
        if cursor > raw_index:
            display_cursor += min(len(before), max(0, min(cursor, start) - raw_index))

        candidate = match.group(0)
        display_token = candidate
        if is_image_attachment_reference(composer, candidate):
            image_index += 1
            display_token = f"[Image #{image_index}]"
        parts.append(display_token)

        if start <= cursor <= end:
            if end > start:
                relative = cursor - start
                if display_token == candidate:
                    display_cursor += relative
                else:
                    display_cursor += min(
                        len(display_token),
                        round((relative / (end - start)) * len(display_token)),
                    )
        elif cursor > end:
            display_cursor += len(display_token)

        raw_index = end

    tail = source[raw_index:]
    parts.append(tail)
    if cursor > raw_index:
        display_cursor += min(len(tail), cursor - raw_index)

    display_text = "".join(parts)
    return display_text, max(0, min(display_cursor, len(display_text)))


def build_render_text(composer: Any, width: int, *, focused: bool | None = None) -> Text:
    composer._last_render_width = max(1, width)
    prefix = prompt_prefix(composer, width)
    continuation = continuation_prefix(composer, width)
    placeholder_text = composer._placeholder_text()
    text_primary = composer._theme.text_primary
    text_muted = composer._theme.text_muted
    text_dim = composer._theme.text_dim
    cursor_style = f"reverse bold {text_primary}" if focused is not False else f"reverse {text_muted}"
    selection_style = f"reverse {composer._theme.selection_bg}"
    renderable = Text(no_wrap=True, overflow="crop", end="")
    if not composer._text and not composer.has_selection:
        renderable.append(prefix, style=text_muted)
        if focused is not False and placeholder_text:
            renderable.append(placeholder_text[:1], style=cursor_style)
            if len(placeholder_text) > 1:
                renderable.append(placeholder_text[1:], style=text_dim)
        elif focused is not False:
            renderable.append(composer.CURSOR_GLYPH, style=cursor_style)
        else:
            renderable.append(placeholder_text, style=text_dim)
        return renderable
    if composer.has_selection:
        rows = composer._visual_row_ranges(max(1, width))[: composer.MAX_VISIBLE_LINES]
        bounds = composer.selection_bounds
        assert bounds is not None
        selection_start, selection_end = bounds
        for index, row in enumerate(rows):
            row_start, row_end = row
            renderable.append(prefix if index == 0 else continuation, style=text_muted)
            if row_start != row_end:
                left = max(row_start, min(selection_start, row_end))
                right = max(row_start, min(selection_end, row_end))
                if row_start < left:
                    renderable.append(composer._text[row_start:left], style=text_primary)
                if left < right:
                    renderable.append(composer._text[left:right], style=selection_style)
                if right < row_end:
                    renderable.append(composer._text[right:row_end], style=text_primary)
            if index < len(rows) - 1:
                renderable.append("\n")
    else:
        display_text, display_cursor_pos = display_text_and_cursor(composer, composer._text, composer._cursor_pos)
        visual = visual_lines(
            composer,
            display_text,
            display_cursor_pos,
            max(1, width),
            include_cursor=focused is not False,
        )[: composer.MAX_VISIBLE_LINES]

        cursor_token = str(getattr(composer, "CURSOR_TOKEN", "") or "")
        for index, line in enumerate(visual):
            renderable.append(prefix if index == 0 else continuation, style=text_muted)
            if cursor_token in line:
                before_cursor, after_cursor = line.split(cursor_token, 1)
                if before_cursor:
                    renderable.append(before_cursor, style=text_primary)
                if after_cursor:
                    renderable.append(after_cursor[:1], style=cursor_style)
                    if len(after_cursor) > 1:
                        renderable.append(after_cursor[1:], style=text_primary)
                else:
                    renderable.append(composer.CURSOR_GLYPH, style=cursor_style)
            elif line:
                renderable.append(line, style=text_primary)
            if index < len(visual) - 1:
                renderable.append("\n")

    return renderable
