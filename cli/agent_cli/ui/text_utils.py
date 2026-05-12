from __future__ import annotations

from rich.cells import cell_len


def _truncate_display_width(value: str, width: int) -> str:
    if width <= 0:
        return ""
    text = str(value or "")
    if cell_len(text) <= width:
        return text
    parts: list[str] = []
    used = 0
    for char in text:
        char_width = cell_len(char)
        if used + char_width > width:
            break
        parts.append(char)
        used += char_width
    return "".join(parts)


def short(value: str, limit: int) -> str:
    text = str(value or "-")
    if cell_len(text) <= limit:
        return text
    if limit <= 3:
        return _truncate_display_width(text, limit)
    return _truncate_display_width(text, max(0, limit - 3)).rstrip() + "..."


def crop_one_line(value: str, width: int) -> str:
    text = str(value).replace("\n", " ").strip()
    if width <= 0:
        return ""
    if cell_len(text) <= width:
        return text
    if width <= 3:
        return _truncate_display_width(text, width)
    return _truncate_display_width(text, width - 3).rstrip() + "..."


def flag_label(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "true":
        return "yes"
    if normalized == "false":
        return "no"
    if normalized in {"", "-"}:
        return "-"
    return normalized


def tool_label(value: str) -> str:
    text = str(value or "-").strip()
    if text in {"", "-"}:
        return "idle"
    return text.replace("_", " ")
