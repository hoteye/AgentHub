from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from rich.console import Console
from rich.text import Text
from textual.events import Resize
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip

from cli.agent_cli.ui.theme import CliTheme, build_theme_styles, default_theme
from cli.agent_cli.ui.transcript_history import TranscriptEntry, render_transcript_entries
from cli.agent_cli.ui.transcript_virtual_list_runtime import (
    TranscriptDisplayItem,
    build_display_items,
    cumulative_offsets,
    item_index_for_entry_id,
    item_index_for_row,
    visible_item_range,
)
from cli.agent_cli.ui.transcript_visual_rendering_runtime import visual_lines_for_entry


@dataclass(slots=True, frozen=True)
class _RenderedDisplayItem:
    strips: tuple[Strip, ...]

    @property
    def height(self) -> int:
        return max(1, len(self.strips))


class TranscriptVirtualList(ScrollView):
    can_focus = False
    _CACHE_WINDOW_PADDING_ITEMS = 24
    _MAX_CACHED_WIDTHS = 2

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._entries_source: list[TranscriptEntry] | None = None
        self._entries: list[TranscriptEntry] = []
        self._display_items: list[TranscriptDisplayItem] = []
        self._item_heights: list[int] = []
        self._item_offsets: list[int] = []
        self._render_width = 0
        self._theme: CliTheme = default_theme()
        self._theme_styles = build_theme_styles(self._theme)
        self._render_console: Console | None = None
        self._render_cache: dict[tuple[int, tuple[object, ...]], _RenderedDisplayItem] = {}
        self._measured_heights: dict[tuple[int, tuple[object, ...]], int] = {}
        self._visible_range: tuple[int, int] = (0, 0)
        self._window_key: tuple[int, int, int, int] | None = None
        self._text_cache = ""
        self._highlighted_entry_ids: set[str] = set()
        self._active_highlighted_entry_id: str | None = None
        self._recent_cache_widths: deque[int] = deque()
        self._recent_window_signatures: dict[int, set[tuple[object, ...]]] = {}
        self._force_follow_bottom: bool = False

    @property
    def text(self) -> str:
        return self._text_cache

    @property
    def visible_range(self) -> tuple[int, int]:
        return self._visible_range

    def load_entries(
        self,
        entries: list[TranscriptEntry],
        *,
        theme: CliTheme | None = None,
        console: Console | None = None,
    ) -> None:
        resolved_theme = theme or default_theme()
        if (
            entries is self._entries_source
            and resolved_theme == self._theme
            and console is self._render_console
        ):
            return
        follow_bottom = self._should_follow_bottom() or self._force_follow_bottom
        self._force_follow_bottom = False
        self._entries_source = entries
        self._entries = list(entries or [])
        self._display_items = build_display_items(self._entries)
        self._theme = resolved_theme
        self._theme_styles = build_theme_styles(self._theme)
        self._render_console = console
        self._text_cache = "\n".join(render_transcript_entries(self._entries))
        self._render_cache.clear()
        self._measured_heights.clear()
        self._recent_cache_widths.clear()
        self._recent_window_signatures.clear()
        self._window_key = None
        self._refresh_layout_for_width(self._current_render_width())
        self.refresh(layout=True)
        if follow_bottom:
            self.scroll_end(animate=False, force=True, immediate=True, x_axis=False)

    def clear_entries(self) -> None:
        self.load_entries([], theme=self._theme, console=self._render_console)

    def scroll_to_item_index(self, index: int, *, align: str = "center") -> bool:
        if not self._display_items:
            return False
        normalized_index = max(0, min(int(index), len(self._display_items) - 1))
        if normalized_index >= len(self._item_offsets):
            return False
        row = int(self._item_offsets[normalized_index])
        viewport_height = max(1, int(self.size.height or 0))
        normalized_align = str(align or "center").strip().lower()
        if normalized_align == "end":
            row = max(0, row - viewport_height + max(1, int(self._item_heights[normalized_index])))
        elif normalized_align == "center":
            row = max(0, row - max(0, viewport_height // 2))
        self.scroll_to(y=row, animate=False, immediate=True, force=True, x=None)
        return True

    def scroll_to_entry(self, entry_id: str, *, align: str = "center") -> bool:
        item_index = item_index_for_entry_id(self._display_items, entry_id)
        if item_index is None:
            return False
        return self.scroll_to_item_index(item_index, align=align)

    def set_highlighted_entry_ids(self, entry_ids: set[str], active_entry_id: str | None) -> None:
        self._highlighted_entry_ids = {
            str(entry_id or "").strip()
            for entry_id in set(entry_ids or set())
            if str(entry_id or "").strip()
        }
        normalized_active = str(active_entry_id or "").strip()
        self._active_highlighted_entry_id = normalized_active or None
        self._render_cache.clear()
        self.refresh(repaint=True, layout=False)

    def on_resize(self, event: Resize) -> None:
        del event
        self._window_key = None
        self._refresh_layout_for_width(self._current_render_width())

    def render_line(self, y: int) -> Strip:
        width = self._current_render_width()
        if width != self._render_width:
            self._refresh_layout_for_width(width)
        if not self._display_items:
            return Strip.blank(max(1, width), self.rich_style)
        try:
            scroll_y = int(self.scroll_offset.y)
        except Exception:
            scroll_y = 0
        absolute_y = scroll_y + int(y)
        self._prepare_visible_window(width=width, scroll_y=scroll_y)
        if absolute_y < 0 or absolute_y >= max(0, self.virtual_size.height):
            return Strip.blank(max(1, width), self.rich_style)
        item_index = item_index_for_row(
            self._item_offsets,
            self._item_heights,
            absolute_y,
        )
        item = self._display_items[item_index]
        if item.kind != "entry" or item.entry is None or item.signature is None:
            return Strip.blank(max(1, width), self.rich_style)
        relative_line = absolute_y - self._item_offsets[item_index]
        rendered = self._render_item(item, width=width)
        if relative_line < 0 or relative_line >= rendered.height:
            return Strip.blank(max(1, width), self.rich_style)
        return rendered.strips[relative_line].adjust_cell_length(max(1, width), self.rich_style)

    def _should_follow_bottom(self) -> bool:
        try:
            if not self._display_items:
                return True
            return int(self.scroll_y) >= max(0, int(self.max_scroll_y) - 1)
        except Exception:
            return True

    def _current_render_width(self) -> int:
        width = 0
        for candidate in (
            getattr(getattr(self, "scrollable_content_region", None), "size", None),
            getattr(self, "content_size", None),
            getattr(self, "size", None),
        ):
            if candidate is None:
                continue
            try:
                width = int(candidate.width)
            except Exception:
                width = 0
            if width > 0:
                break
        return max(20, width)

    def _refresh_layout_for_width(self, width: int) -> None:
        next_width = max(20, int(width or 0))
        self._render_width = next_width
        self._item_heights = []
        for item in self._display_items:
            if item.kind != "entry" or item.signature is None:
                self._item_heights.append(1)
                continue
            cached_height = self._measured_heights.get((next_width, item.signature))
            self._item_heights.append(max(1, int(cached_height or item.estimated_height)))
        self._item_offsets, total_height = cumulative_offsets(self._item_heights)
        self.virtual_size = Size(next_width, max(0, total_height))
        self._window_key = None

    def _prepare_visible_window(self, *, width: int, scroll_y: int) -> None:
        viewport_height = max(1, int(self.size.height or 0))
        window_key = (width, scroll_y, viewport_height, len(self._display_items))
        if window_key == self._window_key:
            return
        start, end = visible_item_range(
            self._item_offsets,
            self._item_heights,
            start_row=scroll_y,
            end_row=scroll_y + viewport_height - 1,
            overscan=2,
        )
        layout_changed = False
        for index in range(start, end):
            item = self._display_items[index]
            if item.kind != "entry" or item.signature is None:
                continue
            rendered = self._render_item(item, width=width)
            if rendered.height != self._item_heights[index]:
                self._measured_heights[(width, item.signature)] = rendered.height
                layout_changed = True
        if layout_changed:
            self._refresh_layout_for_width(width)
            start, end = visible_item_range(
                self._item_offsets,
                self._item_heights,
                start_row=scroll_y,
                end_row=scroll_y + viewport_height - 1,
                overscan=2,
            )
        self._visible_range = (start, end)
        self._window_key = window_key
        self._remember_recent_window(width=width, start=start, end=end)

    def _remember_recent_window(self, *, width: int, start: int, end: int) -> None:
        normalized_width = max(20, int(width or 0))
        try:
            self._recent_cache_widths.remove(normalized_width)
        except ValueError:
            pass
        self._recent_cache_widths.append(normalized_width)
        while len(self._recent_cache_widths) > self._MAX_CACHED_WIDTHS:
            dropped_width = self._recent_cache_widths.popleft()
            self._recent_window_signatures.pop(dropped_width, None)
        self._recent_window_signatures[normalized_width] = self._window_signatures(
            start=start, end=end
        )
        self._prune_caches()

    def _window_signatures(self, *, start: int, end: int) -> set[tuple[object, ...]]:
        keep: set[tuple[object, ...]] = set()
        padded_start = max(0, int(start) - self._CACHE_WINDOW_PADDING_ITEMS)
        padded_end = min(len(self._display_items), int(end) + self._CACHE_WINDOW_PADDING_ITEMS)
        for index in range(padded_start, padded_end):
            item = self._display_items[index]
            if item.kind == "entry" and item.signature is not None:
                keep.add(item.signature)
        highlighted_entry_ids = set(self._highlighted_entry_ids)
        if self._active_highlighted_entry_id:
            highlighted_entry_ids.add(self._active_highlighted_entry_id)
        if not highlighted_entry_ids:
            return keep
        for item in self._display_items:
            if item.kind != "entry" or item.entry is None or item.signature is None:
                continue
            entry_id = str(item.entry.entry_id or "").strip()
            if entry_id and entry_id in highlighted_entry_ids:
                keep.add(item.signature)
        return keep

    def _prune_caches(self) -> None:
        allowed_widths = set(self._recent_cache_widths)
        if not allowed_widths:
            self._render_cache.clear()
            self._measured_heights.clear()
            return
        signatures_by_width = {
            width: self._recent_window_signatures.get(width, set()) for width in allowed_widths
        }
        self._render_cache = {
            cache_key: rendered
            for cache_key, rendered in self._render_cache.items()
            if cache_key[0] in allowed_widths
            and cache_key[1] in signatures_by_width.get(cache_key[0], set())
        }
        self._measured_heights = {
            cache_key: height
            for cache_key, height in self._measured_heights.items()
            if cache_key[0] in allowed_widths
            and cache_key[1] in signatures_by_width.get(cache_key[0], set())
        }

    def _render_item(
        self,
        item: TranscriptDisplayItem,
        *,
        width: int,
    ) -> _RenderedDisplayItem:
        if item.signature is None or item.entry is None:
            return _RenderedDisplayItem(strips=(Strip.blank(max(1, width), self.rich_style),))
        entry_id = str(item.entry.entry_id or "").strip()
        highlight_kind = ""
        if entry_id and entry_id == self._active_highlighted_entry_id:
            highlight_kind = "active"
        elif entry_id and entry_id in self._highlighted_entry_ids:
            highlight_kind = "match"
        cache_key = (max(20, int(width or 0)), item.signature, highlight_kind)
        cached = self._render_cache.get(cache_key)
        if cached is not None:
            return cached
        console = (
            self._render_console
            or getattr(getattr(self, "app", None), "console", None)
            or Console()
        )
        visual_lines = visual_lines_for_entry(
            item.entry,
            width=max(20, int(width or 0)),
            console=console,
            styles=self._theme_styles,
        )
        strips: list[Strip] = []
        for line_text, spans in visual_lines:
            text = Text(str(line_text or ""))
            for start, end, style in list(spans or []):
                if end > start:
                    text.stylize(style, start, end)
            if highlight_kind == "active":
                text.stylize(f"bold reverse {self._theme.text_primary}", 0, len(text.plain))
            elif highlight_kind == "match":
                text.stylize(f"bold {self._theme.accent_primary}", 0, len(text.plain))
            strips.append(
                Strip(text.render(console)).adjust_cell_length(max(1, width), self.rich_style)
            )
        rendered = _RenderedDisplayItem(
            strips=tuple(strips or [Strip.blank(max(1, width), self.rich_style)]),
        )
        self._render_cache[cache_key] = rendered
        return rendered
