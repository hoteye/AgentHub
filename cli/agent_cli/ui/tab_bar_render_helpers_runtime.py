from __future__ import annotations

import unicodedata
from typing import Any

_LEADING_SYMBOL = "⍬"  # ⌬
_ACTIVE_MARKER = ""
_BUSY_MARKER = "●"  # ●
_PENDING_MARKER = "!"
_UNREAD_MARKER = "*"
_DIRTY_MARKER = "~"
_CLOSE_MARKER = "×"
_RAIL_ACTIVE_INDICATOR = "▕"
_RAIL_ACTIVE_BOTTOM_CORNER = "\U0001fb7f"
_RAIL_ACTIVE_TOP_CORNER = "\U0001fb7e"
_LEADING_PADDING = " "
_TRAILING_PADDING = " "
_SEPARATOR = " │ "
_NEW_BUTTON = "[+]"
_MAX_LABEL_CELLS = 24
_RAIL_WIDTH = 2
_RAIL_TAB_HEIGHT = 3
_RAIL_COMPACT_WIDTH = 1
_COMPACT_THRESHOLD = 64
_COMPACT_ACTIVE_TOP = "▕"
_RAIL_THEME_BG = "#11161c"
_RAIL_ALT_BG = "#343a43"
_RAIL_TEXT = "#c9d1d9"
_RAIL_TEXT_DIM = "#6e7681"
_ELLIPSIS = "…"


def _cell_width(s: str) -> int:
    w = 0
    for ch in s:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w


def _crop_cells(value: str, max_cells: int) -> str:
    text = str(value or "")
    if max_cells <= 0:
        return ""
    if _cell_width(text) <= max_cells:
        return text
    ellipsis_width = _cell_width(_ELLIPSIS)
    if max_cells <= ellipsis_width:
        return _ELLIPSIS[:max_cells]
    budget = max_cells - ellipsis_width
    result = ""
    used = 0
    for ch in text:
        width = _cell_width(ch)
        if used + width > budget:
            break
        result += ch
        used += width
    return f"{result}{_ELLIPSIS}"


def _lighten_hex_color(color: str, *, ratio: float = 0.16) -> str:
    candidate = str(color or "").strip()
    if not (len(candidate) == 7 and candidate.startswith("#")):
        return candidate or _RAIL_ALT_BG
    try:
        channels = [int(candidate[idx : idx + 2], 16) for idx in (1, 3, 5)]
    except ValueError:
        return candidate or _RAIL_ALT_BG
    normalized = max(0.0, min(1.0, float(ratio)))
    lightened = [
        max(0, min(255, int(round(channel + (255 - channel) * normalized)))) for channel in channels
    ]
    return "#{:02x}{:02x}{:02x}".format(*lightened)


def _darken_hex_color(color: str, *, factor: float = 0.75) -> str:
    candidate = str(color or "").strip()
    if not (len(candidate) == 7 and candidate.startswith("#")):
        return candidate or _RAIL_THEME_BG
    try:
        channels = [int(candidate[idx : idx + 2], 16) for idx in (1, 3, 5)]
    except ValueError:
        return candidate or _RAIL_THEME_BG
    darkened = [max(0, min(255, int(round(channel * factor)))) for channel in channels]
    return "#{:02x}{:02x}{:02x}".format(*darkened)


def _invert_hex_color(color: str) -> str:
    candidate = str(color or "").strip()
    if not (len(candidate) == 7 and candidate.startswith("#")):
        return _RAIL_THEME_BG
    try:
        channels = [int(candidate[idx : idx + 2], 16) for idx in (1, 3, 5)]
    except ValueError:
        return _RAIL_THEME_BG
    inverted = [255 - c for c in channels]
    return "#{:02x}{:02x}{:02x}".format(*inverted)


def _rail_tab_code(index: int, *, active: bool = False) -> str:
    alphabet = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    code = alphabet[index] if 0 <= index < len(alphabet) else "Z"
    return code


def _pad_rail_line(value: str, width: int, *, align: str = "center") -> str:
    cropped = _crop_cells(value, max(1, width))
    remaining = max(0, width - _cell_width(cropped))
    if align == "left":
        return f"{cropped}{' ' * remaining}"
    if align == "right":
        return f"{' ' * remaining}{cropped}"
    left = (remaining + 1) // 2
    right = remaining - left
    return f"{' ' * left}{cropped}{' ' * right}"


def _rail_status_text(tab: Any) -> str:
    markers = ""
    if tab.is_busy:
        markers += _BUSY_MARKER
    if tab.has_pending_approval:
        markers += _PENDING_MARKER
    if tab.has_unread_output:
        markers += _UNREAD_MARKER
    elif tab.is_dirty:
        markers += _DIRTY_MARKER
    return markers


def _merge_status_with_rail_edge(status_text: str, edge_text: str) -> str:
    if not status_text:
        return edge_text
    if not edge_text:
        return status_text
    return f"{status_text[:1]}{edge_text[1:]}"
