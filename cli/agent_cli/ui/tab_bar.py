from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from rich.style import Style as RichStyle
from rich.text import Text
from textual.events import MouseDown, MouseUp
from textual.widgets import Static


@dataclass
class TabInfo:
    tab_id: str
    label: str = ""
    is_active: bool = False
    is_busy: bool = False
    has_pending_approval: bool = False
    has_unread_output: bool = False
    is_dirty: bool = False


_LEADING_SYMBOL = "⍬"  # ⌬
_ACTIVE_MARKER = ""
_BUSY_MARKER = "●"  # ●
_PENDING_MARKER = "!"
_UNREAD_MARKER = "*"
_DIRTY_MARKER = "~"
_CLOSE_MARKER = "×"
_RAIL_ACTIVE_INDICATOR = "▕"
_LEADING_PADDING = " "
_TRAILING_PADDING = " "
_SEPARATOR = " │ "
_NEW_BUTTON = "[+]"
_MAX_LABEL_CELLS = 24
_RAIL_WIDTH = 2
_RAIL_TAB_HEIGHT = 3
_RAIL_COMPACT_WIDTH = 1
_COMPACT_THRESHOLD = 64
_COMPACT_ACTIVE_TOP = "│"
_COMPACT_ACTIVE_BOTTOM = "│"
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


class TabBar(Static):
    DEFAULT_CSS = """
    TabBar {
        height: 1;
        width: 1fr;
        padding: 0 1;
        content-align: left middle;
    }
    """

    def __init__(
        self,
        *args: Any,
        orientation: Literal["horizontal", "vertical"] = "horizontal",
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.orientation = orientation
        self._tabs: list[TabInfo] = []
        self._leading_symbol: str = _LEADING_SYMBOL
        self._tab_spans: list[tuple[str, int, int]] = []
        self._close_spans: list[tuple[str, int, int]] = []
        self._close_hitboxes: list[tuple[str, int, int, int]] = []
        self._rail_theme_bg: str = _RAIL_THEME_BG
        self._rail_alt_bg: str = _lighten_hex_color(_RAIL_THEME_BG)
        self._rail_text: str = _RAIL_TEXT
        self._rail_text_dim: str = _RAIL_TEXT_DIM
        self._compact: bool = False

    @property
    def is_compact(self) -> bool:
        return self._compact

    def update_compact(self, app_width: int) -> None:
        compact = app_width < _COMPACT_THRESHOLD
        if compact == self._compact:
            return
        self._compact = compact
        target_width = _RAIL_COMPACT_WIDTH if compact else _RAIL_WIDTH
        self.styles.width = target_width
        self.refresh(repaint=True, layout=True)

    def update_tabs(self, tabs: list[TabInfo]) -> None:
        self._tabs = list(tabs)
        self.refresh(repaint=True, layout=False)

    def set_leading_symbol(self, symbol: str) -> None:
        self._leading_symbol = symbol
        self.refresh(repaint=True, layout=False)

    def set_rail_palette(
        self,
        *,
        theme_bg: str,
        text: str,
        text_dim: str,
        alternate_bg: str | None = None,
        dark_bg: str | None = None,
    ) -> None:
        self._rail_theme_bg = theme_bg
        self._rail_alt_bg = alternate_bg or dark_bg or _lighten_hex_color(theme_bg)
        self._rail_text = text
        self._rail_text_dim = text_dim
        self.refresh(repaint=True, layout=False)

    def render(self) -> Text:
        if self.orientation == "vertical":
            return self._render_vertical()
        return self._render_horizontal()

    def _render_horizontal(self) -> Text:
        text = Text(no_wrap=True, overflow="ellipsis", end="")
        self._tab_spans = []
        self._close_spans = []
        self._close_hitboxes = []
        cell_offset = 0

        # Keep the leading icon visually balanced before the tab strip.
        text.append(_LEADING_PADDING)
        cell_offset += _cell_width(_LEADING_PADDING)
        text.append(self._leading_symbol, style=RichStyle(dim=True))
        cell_offset += _cell_width(self._leading_symbol)
        text.append(_TRAILING_PADDING)
        cell_offset += _cell_width(_TRAILING_PADDING)

        if not self._tabs:
            return text

        for i, tab in enumerate(self._tabs):
            if i > 0:
                text.append(_SEPARATOR, style=RichStyle(dim=True))
                cell_offset += _cell_width(_SEPARATOR)

            label = _crop_cells(tab.label or tab.tab_id, _MAX_LABEL_CELLS)
            tab_label = f" {label} "
            start = cell_offset
            if tab.is_active:
                text.append(tab_label, style=RichStyle(reverse=True))
            else:
                text.append(tab_label, style=RichStyle(dim=True))
            cell_offset += _cell_width(tab_label)

            if tab.is_busy:
                text.append(_BUSY_MARKER, style=RichStyle(color="yellow"))
                cell_offset += _cell_width(_BUSY_MARKER)
            if tab.has_pending_approval:
                text.append(_PENDING_MARKER, style=RichStyle(color="red", bold=True))
                cell_offset += _cell_width(_PENDING_MARKER)
            if tab.has_unread_output:
                text.append(_UNREAD_MARKER, style=RichStyle(color="cyan", bold=True))
                cell_offset += _cell_width(_UNREAD_MARKER)
            elif tab.is_dirty:
                text.append(_DIRTY_MARKER, style=RichStyle(color="cyan"))
                cell_offset += _cell_width(_DIRTY_MARKER)

            self._tab_spans.append((tab.tab_id, start, cell_offset))
            if len(self._tabs) > 1 and not tab.is_busy:
                close_start = cell_offset
                close_style = RichStyle(reverse=tab.is_active, dim=not tab.is_active)
                text.append(_CLOSE_MARKER, style=close_style)
                cell_offset += _cell_width(_CLOSE_MARKER)
                self._close_spans.append((tab.tab_id, close_start, cell_offset))

        return text

    def _render_vertical(self) -> Text:
        text = Text(no_wrap=True, overflow="ellipsis", end="")
        self._tab_spans = []
        self._close_spans = []
        self._close_hitboxes = []
        if not self._tabs:
            return text

        if self._compact:
            return self._render_vertical_compact(text)

        width = self._rail_width()
        top_padding = self._vertical_top_padding()
        if top_padding:
            text.append("\n" * top_padding)
        for index, tab in enumerate(self._tabs):
            bg = _darken_hex_color(self._rail_theme_bg, factor=0.75)
            base_style = RichStyle(
                color=self._rail_text if tab.is_active else self._rail_text_dim,
                bgcolor=bg,
                bold=tab.is_active,
            )
            tab_start_y = top_padding + index * _RAIL_TAB_HEIGHT
            tab_end_y = tab_start_y + _RAIL_TAB_HEIGHT
            label_line = tab.tab_id[-1]
            top_line = self._rail_status_text(tab) or " "
            bottom_line = "▁"
            content_width = width - _cell_width(_RAIL_ACTIVE_INDICATOR) if tab.is_active else width

            align = "right" if tab.is_active else "left"
            if index > 0:
                text.append("\n")
            text.append(self._pad_rail_line(top_line, content_width, align=align), style=base_style)
            if tab.is_active:
                text.append(_RAIL_ACTIVE_INDICATOR, style=base_style)
            text.append("\n")
            text.append(
                self._pad_rail_line(label_line, content_width, align=align), style=base_style
            )
            if tab.is_active:
                text.append(_RAIL_ACTIVE_INDICATOR, style=base_style)
            text.append("\n")
            text.append(
                self._pad_rail_line(bottom_line, content_width, align=align), style=base_style
            )
            if tab.is_active:
                text.append(_RAIL_ACTIVE_INDICATOR, style=base_style)

            self._tab_spans.append((tab.tab_id, tab_start_y, tab_end_y))

        return text

    def _render_vertical_compact(self, text: Text) -> Text:
        tab_height = 3
        top_padding = self._vertical_top_padding_for(tab_height)
        if top_padding:
            text.append("\n" * top_padding)
        for index, tab in enumerate(self._tabs):
            bg = _darken_hex_color(self._rail_theme_bg, factor=0.75)
            base_style = RichStyle(
                color=self._rail_text if tab.is_active else self._rail_text_dim,
                bgcolor=bg,
                bold=tab.is_active,
            )
            tab_start_y = top_padding + index * tab_height
            tab_end_y = tab_start_y + tab_height
            code = self._rail_tab_code(index, active=tab.is_active)
            status_text = self._rail_status_text(tab)

            if index > 0:
                text.append("\n")
            if status_text:
                text.append(status_text[:1], style=base_style)
            elif tab.is_active:
                text.append(_COMPACT_ACTIVE_TOP, style=base_style)
            else:
                text.append(" ", style=base_style)
            text.append("\n")
            text.append(code, style=base_style)
            text.append("\n")
            if tab.is_active:
                text.append(_COMPACT_ACTIVE_BOTTOM, style=base_style)
            else:
                text.append(" ", style=base_style)

            self._tab_spans.append((tab.tab_id, tab_start_y, tab_end_y))

        return text

    def _rail_width(self) -> int:
        measured = int(getattr(getattr(self, "size", None), "width", 0) or 0)
        return max(1, measured or _RAIL_WIDTH)

    def _rail_height(self) -> int:
        return int(getattr(getattr(self, "size", None), "height", 0) or 0)

    def _vertical_top_padding(self) -> int:
        return self._vertical_top_padding_for(_RAIL_TAB_HEIGHT if not self._compact else 3)

    def _vertical_top_padding_for(self, tab_height: int) -> int:
        measured_height = self._rail_height()
        content_height = len(self._tabs) * tab_height
        if measured_height <= content_height:
            return 0
        return max(0, (measured_height - content_height) // 2)

    @staticmethod
    def _rail_tab_code(index: int, *, active: bool = False) -> str:
        alphabet = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        code = alphabet[index] if 0 <= index < len(alphabet) else "Z"
        return code

    def _pad_rail_line(self, value: str, width: int, *, align: str = "center") -> str:
        cropped = _crop_cells(value, max(1, width))
        remaining = max(0, width - _cell_width(cropped))
        if align == "left":
            return f"{cropped}{' ' * remaining}"
        if align == "right":
            return f"{' ' * remaining}{cropped}"
        left = (remaining + 1) // 2
        right = remaining - left
        return f"{' ' * left}{cropped}{' ' * right}"

    @staticmethod
    def _rail_status_text(tab: TabInfo) -> str:
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

    def on_mouse_down(self, event: MouseDown) -> None:
        if self.orientation == "vertical":
            self._handle_tab_pointer_event(event)

    def on_mouse_up(self, event: MouseUp) -> None:
        self._handle_tab_pointer_event(event)

    def _handle_tab_pointer_event(self, event: MouseDown | MouseUp) -> None:
        if event.button != 1:
            return
        if self.orientation == "vertical":
            self._on_vertical_pointer_event(event)
            return
        x = event.x - 1  # account for left padding
        for tab_id, start, end in self._close_spans:
            if start <= x < end:
                event.stop()
                event.prevent_default()
                app = self.app
                mgr = getattr(app, "_tab_manager", None)
                if mgr is not None and mgr.close_tab(tab_id) is not None:
                    app._refresh_top_title_bar()
                    app._focus_input()
                return
        for tab_id, start, end in self._tab_spans:
            if start <= x < end:
                event.stop()
                event.prevent_default()
                app = self.app
                mgr = getattr(app, "_tab_manager", None)
                if mgr is not None and tab_id != mgr.active_tab_id:
                    if mgr.switch_to_tab(tab_id):
                        app._refresh_top_title_bar()
                        app._focus_input()
                return

    def _on_vertical_pointer_event(self, event: MouseDown | MouseUp) -> None:
        x = int(event.x)
        y = int(event.y)
        for tab_id, start_x, end_x, hit_y in self._close_hitboxes:
            if hit_y == y and start_x <= x < end_x:
                event.stop()
                event.prevent_default()
                app = self.app
                mgr = getattr(app, "_tab_manager", None)
                if mgr is not None and mgr.close_tab(tab_id) is not None:
                    app._refresh_top_title_bar()
                    app._focus_input()
                return
        for tab_id, start_y, end_y in self._tab_spans:
            if start_y <= y < end_y:
                event.stop()
                event.prevent_default()
                app = self.app
                mgr = getattr(app, "_tab_manager", None)
                if mgr is not None and tab_id != mgr.active_tab_id:
                    if mgr.switch_to_tab(tab_id):
                        app._refresh_top_title_bar()
                        app._focus_input()
                return
