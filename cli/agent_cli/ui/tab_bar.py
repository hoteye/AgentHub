from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from rich.style import Style as RichStyle
from rich.text import Text
from textual.events import MouseDown, MouseUp
from textual.widgets import Static

from .tab_bar_render_helpers_runtime import (
    _ACTIVE_MARKER as _ACTIVE_MARKER,
)
from .tab_bar_render_helpers_runtime import (
    _BUSY_MARKER,
    _CLOSE_MARKER,
    _COMPACT_ACTIVE_TOP,
    _COMPACT_THRESHOLD,
    _DIRTY_MARKER,
    _LEADING_PADDING,
    _LEADING_SYMBOL,
    _MAX_LABEL_CELLS,
    _PENDING_MARKER,
    _RAIL_ACTIVE_BOTTOM_CORNER,
    _RAIL_ACTIVE_INDICATOR,
    _RAIL_ACTIVE_TOP_CORNER,
    _RAIL_COMPACT_WIDTH,
    _RAIL_TAB_HEIGHT,
    _RAIL_TEXT,
    _RAIL_TEXT_DIM,
    _RAIL_THEME_BG,
    _RAIL_WIDTH,
    _SEPARATOR,
    _TRAILING_PADDING,
    _UNREAD_MARKER,
    _cell_width,
    _crop_cells,
    _darken_hex_color,
    _lighten_hex_color,
    _merge_status_with_rail_edge,
    _pad_rail_line,
    _rail_status_text,
    _rail_tab_code,
)
from .tab_bar_render_helpers_runtime import (
    _ELLIPSIS as _ELLIPSIS,
)
from .tab_bar_render_helpers_runtime import (
    _NEW_BUTTON as _NEW_BUTTON,
)
from .tab_bar_render_helpers_runtime import (
    _RAIL_ALT_BG as _RAIL_ALT_BG,
)
from .tab_bar_render_helpers_runtime import (
    _invert_hex_color as _invert_hex_color,
)


@dataclass
class TabInfo:
    tab_id: str
    label: str = ""
    is_active: bool = False
    is_busy: bool = False
    has_pending_approval: bool = False
    has_unread_output: bool = False
    is_dirty: bool = False


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
            status_text = self._rail_status_text(tab)
            if index == 0:
                top_border = "▔" if tab.is_active else "▔" * width
                top_line = self._merge_status_with_rail_edge(status_text, top_border)
            else:
                top_line = status_text or " "
            bottom_line = "▁" * width if not tab.is_active else "▁"
            content_width = width - _cell_width(_RAIL_ACTIVE_INDICATOR) if tab.is_active else width

            align = "right" if tab.is_active else "left"
            if index > 0:
                text.append("\n")
            text.append(self._pad_rail_line(top_line, content_width, align=align), style=base_style)
            if tab.is_active:
                top_corner = _RAIL_ACTIVE_TOP_CORNER if index == 0 else _RAIL_ACTIVE_INDICATOR
                text.append(top_corner, style=base_style)
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
                text.append(_RAIL_ACTIVE_BOTTOM_CORNER, style=base_style)

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
            if index == 0:
                first_line = _RAIL_ACTIVE_TOP_CORNER if tab.is_active else "▔"
                text.append(
                    self._merge_status_with_rail_edge(status_text, first_line)[:1],
                    style=base_style,
                )
            elif status_text:
                text.append(status_text[:1], style=base_style)
            elif tab.is_active:
                text.append(_COMPACT_ACTIVE_TOP, style=base_style)
            else:
                text.append(" ", style=base_style)
            text.append("\n")
            text.append(code, style=base_style)
            text.append("\n")
            if tab.is_active:
                text.append(_RAIL_ACTIVE_BOTTOM_CORNER, style=base_style)
            else:
                text.append("▁", style=base_style)

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
        return _rail_tab_code(index, active=active)

    def _pad_rail_line(self, value: str, width: int, *, align: str = "center") -> str:
        return _pad_rail_line(value, width, align=align)

    @staticmethod
    def _rail_status_text(tab: TabInfo) -> str:
        return _rail_status_text(tab)

    @staticmethod
    def _merge_status_with_rail_edge(status_text: str, edge_text: str) -> str:
        return _merge_status_with_rail_edge(status_text, edge_text)

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
