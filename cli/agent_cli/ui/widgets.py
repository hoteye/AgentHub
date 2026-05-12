from __future__ import annotations

from rich.style import Style as RichStyle
from rich.text import Text
from textual.events import Leave, MouseDown, MouseMove, MouseUp
from textual.strip import Strip
from textual.widgets import Static, TextArea

from cli.agent_cli.debug_timeline import append_debug_jsonl, timeline_debug_enabled
from cli.agent_cli.ui import (
    transcript_selection_runtime,
    widgets_popup_runtime,
    widgets_quote_logging_runtime,
    widgets_runtime,
    widgets_transcript_render_runtime,
)
from cli.agent_cli.ui.presentation import PresentationSettings
from cli.agent_cli.ui.theme import CliTheme, default_theme


class TranscriptArea(TextArea):
    can_focus = False
    MULTI_CLICK_TIMEOUT_SECONDS = 0.4
    WORD_SEPARATORS = "`~!@#$%^&*()-=+[{]}\\|;:'\",.<>/?"

    def __init__(self, text: str = "", **kwargs) -> None:
        self._line_styles: list[list[tuple[int, int, RichStyle]]] = []
        self._base_line_cache: dict[int, Text] = {}
        self._loaded_transcript_lines: list[str] | None = None
        self._loaded_transcript_line_styles: list[list[tuple[int, int, RichStyle]]] | None = None
        self._logged_quote_render_keys: set[tuple[int, int]] = set()
        super().__init__(text, **kwargs)
        self.cursor_blink = False
        self.show_cursor = False
        self.highlight_cursor_line = False
        self._last_click_at = 0.0
        self._last_click_cell: tuple[int, int] | None = None
        self._click_streak = 0
        self._last_right_click_at = 0.0
        self._last_right_click_cell: tuple[int, int] | None = None
        self._right_click_streak = 0
        self._right_click_copy_pending = False
        self._right_click_copy_handled_on_mouse_down = False
        self._right_click_paste_text: str | None = None
        self._last_right_click_copied_text: str | None = None
        self._drag_anchor_location: tuple[int, int] | None = None
        self._preview_click_candidate: tuple[int, int] | None = None
        self._preview_hover_target_span: tuple[int, int, int] | None = None
        self._is_drag_selecting = False
        self._suppress_left_mouse_up_copy = False

    def load_transcript(
        self,
        lines: list[str],
        *,
        line_styles: list[list[tuple[int, int, RichStyle]]] | None = None,
    ) -> None:
        normalized_lines = [str(line or "") for line in list(lines or [])]
        normalized_styles = [
            list(spans) for spans in list(line_styles or [[] for _ in normalized_lines])
        ]
        if (
            self._loaded_transcript_lines == normalized_lines
            and self._loaded_transcript_line_styles == normalized_styles
        ):
            return
        self._line_styles = normalized_styles
        self._preview_hover_target_span = None
        self._base_line_cache.clear()
        self._logged_quote_render_keys.clear()
        self._loaded_transcript_lines = list(normalized_lines)
        self._loaded_transcript_line_styles = [list(spans) for spans in normalized_styles]
        self._log_quote_lines("transcript.load", lines=normalized_lines)
        super().load_text("\n".join(normalized_lines))

    def load_text(self, text: str) -> None:
        self._line_styles = []
        self._preview_hover_target_span = None
        self._base_line_cache.clear()
        self._loaded_transcript_lines = None
        self._loaded_transcript_line_styles = None
        self._logged_quote_render_keys.clear()
        super().load_text(text)

    def transcript_scroll_offset(self) -> tuple[int, int]:
        try:
            offset = self.scroll_offset
        except Exception:
            return (0, 0)
        try:
            return (int(offset.x), int(offset.y))
        except Exception:
            pass
        try:
            return (int(offset[0]), int(offset[1]))
        except Exception:
            return (0, 0)

    def transcript_should_follow_bottom(self) -> bool:
        try:
            if not self.text:
                return True
            _, scroll_y = self.transcript_scroll_offset()
            return int(scroll_y) >= max(0, int(self.max_scroll_y) - 1)
        except Exception:
            return True

    def restore_transcript_viewport(self, *, scroll_x: int = 0, scroll_y: int = 0) -> None:
        try:
            self.scroll_to(
                x=max(0, int(scroll_x)),
                y=max(0, int(scroll_y)),
                animate=False,
                immediate=True,
                force=True,
            )
        except Exception:
            return

    def get_line(self, line_index: int) -> Text:
        cached = self._base_line_cache.get(line_index)
        if cached is None:
            line = super().get_line(line_index)
            if 0 <= line_index < len(self._line_styles):
                for start, end, style in self._line_styles[line_index]:
                    if end > start:
                        line.stylize(style, start, end)
            self._base_line_cache[line_index] = line.copy()
            cached = self._base_line_cache[line_index]
        line = cached.copy()
        hover_span = self._preview_hover_target_span
        if hover_span is not None:
            hover_row, hover_start, hover_end = hover_span
            if hover_row == line_index and hover_end > hover_start:
                line.stylize(RichStyle(underline=True), hover_start, hover_end)
        return line

    def _build_highlight_map(self) -> None:
        self._base_line_cache.clear()
        line_cache = getattr(self, "_line_cache", None)
        if line_cache is not None:
            try:
                line_cache.clear()
            except Exception:
                pass
        highlights = getattr(self, "_highlights", None)
        if highlights is not None:
            try:
                highlights.clear()
            except Exception:
                pass

    def render_line(self, y: int):
        strip = self._render_transcript_line(y)
        if not timeline_debug_enabled():
            return strip
        try:
            scroll_y = int(self.scroll_offset[1])
        except Exception:
            scroll_y = 0
        absolute_y = scroll_y + int(y)
        try:
            line_info = self.wrapped_document._offset_to_line_info[absolute_y]
        except Exception:
            line_info = None
        if line_info is None:
            return strip
        line_index, section_offset = line_info
        key = (int(line_index), int(section_offset))
        if key in self._logged_quote_render_keys:
            return strip
        try:
            document_line = str(self.document[line_index])
        except Exception:
            document_line = ""
        if ">" not in document_line:
            return strip
        self._logged_quote_render_keys.add(key)
        probe_line = self.get_line(line_index)
        probe_line.tab_size = self.indent_width
        probe_line.set_length(len(probe_line) + (1 if self.show_cursor else 0))
        try:
            probe_segments = list(probe_line.render(self.app.console))
        except Exception:
            probe_segments = []
        append_debug_jsonl(
            "tui_render_debug.jsonl",
            stage="transcript.render_line",
            module_file=__file__,
            **widgets_runtime.render_line_debug_payload(
                y=int(y),
                absolute_y=absolute_y,
                line_index=int(line_index),
                section_offset=int(section_offset),
                document_line=document_line,
                strip_text=strip.text,
                strip_segments=list(strip._segments),
                probe_line_style=probe_line.style,
                probe_line_spans=probe_line.spans,
                probe_render_segments=probe_segments,
                show_cursor=bool(self.show_cursor),
                highlight_cursor_line=bool(self.highlight_cursor_line),
                selection_start=self.selection.start,
                selection_end=self.selection.end,
                has_cursor=bool(getattr(self, "_has_cursor", False)),
                draw_cursor=bool(getattr(self, "_draw_cursor", False)),
                language=getattr(self, "language", None),
                theme=getattr(self, "theme", None),
                highlight_query=bool(getattr(self, "_highlight_query", None)),
                highlight_ranges=list(getattr(self, "_highlights", {}).get(line_index, [])),
                rich_style=self.rich_style,
                visual_style=self.visual_style.rich_style,
                serialize_style_fn=widgets_runtime.serialize_rich_style,
            ),
        )
        return strip

    def _render_transcript_line(self, y: int) -> Strip:
        return widgets_transcript_render_runtime.render_transcript_line(self, y)

    def _blank_transcript_strip(self, theme) -> Strip:
        base_style = theme.base_style if theme and theme.base_style is not None else self.rich_style
        return Strip.blank(self.size.width, base_style)

    def on_mouse_down(self, event: MouseDown) -> None:
        transcript_selection_runtime.on_mouse_down(self, event)

    def on_mouse_move(self, event: MouseMove) -> None:
        transcript_selection_runtime.on_mouse_move(self, event)

    def on_mouse_up(self, event: MouseUp) -> None:
        transcript_selection_runtime.on_mouse_up(self, event)

    def on_leave(self, event: Leave) -> None:
        transcript_selection_runtime.on_leave(self, event)

    def copy_selection_to_clipboard(self) -> bool:
        return transcript_selection_runtime.copy_selection_to_clipboard(self)

    def _paste_text_into_prompt(self, text: str) -> None:
        transcript_selection_runtime.paste_text_into_prompt(self, text)

    def _register_click_streak(self, x: int, y: int) -> int:
        return transcript_selection_runtime.register_click_streak(self, x, y)

    def _register_right_click_streak(self, x: int, y: int) -> int:
        return transcript_selection_runtime.register_right_click_streak(self, x, y)

    def _end_drag_selection(self) -> None:
        transcript_selection_runtime.end_drag_selection(self)

    @classmethod
    def _is_word_separator(cls, char: str) -> bool:
        return char in cls.WORD_SEPARATORS

    def _select_word_at(self, row: int, column: int) -> None:
        transcript_selection_runtime.select_word_at(self, row, column)

    def _log_quote_lines(self, stage: str, *, lines: list[str]) -> None:
        widgets_quote_logging_runtime.log_quote_lines(
            self,
            stage=stage,
            lines=lines,
            module_file=__file__,
        )


class SlashCommandPopup(Static):
    can_focus = False
    MAX_VISIBLE_ITEMS = 6

    def __init__(
        self,
        *,
        presentation: PresentationSettings | None = None,
        theme: CliTheme | None = None,
        **kwargs,
    ) -> None:
        super().__init__("", **kwargs)
        self._theme = theme or (presentation.theme if presentation is not None else default_theme())
        self._items: list[dict[str, str]] = []
        self._selected_index = 0
        self._query = ""
        self._scroll_top = 0
        self._mode = "slash"

    def set_items(
        self,
        items: list[dict[str, str]],
        selected_index: int,
        query: str = "",
        *,
        mode: str = "slash",
    ) -> None:
        popup_state = widgets_runtime.popup_state(
            items=items,
            selected_index=selected_index,
            query=query,
            mode=mode,
            current_scroll_top=self._scroll_top,
            max_visible_items=self.MAX_VISIBLE_ITEMS,
            popup_scroll_top_fn=widgets_popup_runtime.popup_scroll_top,
        )
        self._items = popup_state["items"]
        self._selected_index = popup_state["selected_index"]
        self._query = popup_state["query"]
        self._mode = popup_state["mode"]
        self._scroll_top = popup_state["scroll_top"]
        self.refresh(repaint=True, layout=False)

    def set_presentation(
        self,
        *,
        presentation: PresentationSettings | None = None,
        theme: CliTheme | None = None,
    ) -> None:
        self._theme = theme or (presentation.theme if presentation is not None else self._theme)
        self.refresh(repaint=True, layout=False)

    def visible_line_count(self) -> int:
        return widgets_runtime.popup_visible_line_count(
            item_count=len(self._items),
            max_visible_items=self.MAX_VISIBLE_ITEMS,
        )

    def render(self) -> Text:
        return widgets_popup_runtime.render_popup(
            theme=self._theme,
            items=self._items,
            selected_index=self._selected_index,
            scroll_top=self._scroll_top,
            visible=self.visible_line_count(),
            highlighted_text_fn=self._highlighted_text,
        )

    def _highlighted_text(self, value: str, *, style: str, highlight_style: str) -> Text:
        return widgets_popup_runtime.highlighted_text(
            value,
            query=self._query,
            style=style,
            highlight_style=highlight_style,
        )
