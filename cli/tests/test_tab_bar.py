from __future__ import annotations

import unittest

from rich.text import Text

from cli.agent_cli.ui.tab_bar import (
    TabBar,
    TabInfo,
    _cell_width,
    _crop_cells,
    _lighten_hex_color,
)


class TestTabBar(unittest.TestCase):
    def test_default_css_aligns_tabs_from_left(self):
        assert "content-align: left middle;" in TabBar.DEFAULT_CSS
        assert "content-align: center middle;" not in TabBar.DEFAULT_CSS

    def test_theme_css_keeps_vertical_tab_rail_pointer_coordinates_top_based(self):
        from cli.agent_cli.ui.theme import BUILTIN_THEMES
        from cli.agent_cli.ui.theme_runtime import build_app_css

        css = build_app_css(BUILTIN_THEMES["reference_dark"])

        assert "#tab_bar" in css
        assert "width: 2;" in css
        assert "content-align: left top;" in css

    def test_render_single_active_tab(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="AgentHub", is_active=True),
            ]
        )
        rendered = bar.render()
        assert isinstance(rendered, Text)
        plain = rendered.plain
        assert "AgentHub" in plain
        assert "⍬" in plain

    def test_render_keeps_icon_before_tabs(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="Main", is_active=True),
                TabInfo(tab_id="tab-1", label="Fork", is_active=False),
            ]
        )
        plain = bar.render().plain
        assert plain.index("⍬") < plain.index("Main") < plain.index("Fork")

    def test_render_balances_icon_padding_before_first_tab(self):
        bar = TabBar()
        bar.update_tabs([TabInfo(tab_id="main", label="Main", is_active=True)])

        plain = bar.render().plain

        assert plain.startswith(" ⍬  Main ")

    def test_render_uses_visible_separator_between_tabs(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="Main", is_active=True),
                TabInfo(tab_id="tab-1", label="Fork", is_active=False),
            ]
        )

        plain = bar.render().plain

        assert "│" in plain
        assert plain.index("Main") < plain.index("│") < plain.index("Fork")

    def test_render_multiple_tabs(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="tab-1", label="Chat 1", is_active=True),
                TabInfo(tab_id="tab-2", label="Chat 2", is_active=False),
            ]
        )
        rendered = bar.render()
        plain = rendered.plain
        assert "Chat 1" in plain
        assert "Chat 2" in plain

    def test_render_busy_indicator(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="tab-1", label="Chat", is_active=False, is_busy=True),
            ]
        )
        rendered = bar.render()
        assert "●" in rendered.plain

    def test_render_pending_approval(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="tab-1", label="Chat", is_active=False, has_pending_approval=True),
            ]
        )
        rendered = bar.render()
        assert "!" in rendered.plain

    def test_render_busy_and_pending_indicators_together(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(
                    tab_id="tab-1",
                    label="Chat",
                    is_active=False,
                    is_busy=True,
                    has_pending_approval=True,
                ),
            ]
        )
        rendered = bar.render()
        assert "●!" in rendered.plain

    def test_render_unread_indicator(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="tab-1", label="Chat", is_active=False, has_unread_output=True),
            ]
        )
        rendered = bar.render()
        assert "*" in rendered.plain

    def test_render_dirty_indicator_when_no_unread_output(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="tab-1", label="Chat", is_active=False, is_dirty=True),
            ]
        )
        rendered = bar.render()
        assert "~" in rendered.plain

    def test_unread_indicator_takes_precedence_over_dirty_indicator(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(
                    tab_id="tab-1",
                    label="Chat",
                    is_active=False,
                    has_unread_output=True,
                    is_dirty=True,
                ),
            ]
        )
        rendered = bar.render()
        assert "*" in rendered.plain
        assert "~" not in rendered.plain

    def test_render_busy_pending_and_unread_indicators_together(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(
                    tab_id="tab-1",
                    label="Chat",
                    is_active=False,
                    is_busy=True,
                    has_pending_approval=True,
                    has_unread_output=True,
                ),
            ]
        )
        rendered = bar.render()
        assert "●!*" in rendered.plain

    def test_render_close_marker_for_idle_tabs_when_multiple_tabs_exist(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="Main", is_active=True),
                TabInfo(tab_id="tab-1", label="Fork", is_active=False),
            ]
        )
        rendered = bar.render()
        assert "×" in rendered.plain
        assert len(bar._close_spans) == 2

    def test_render_no_close_marker_for_single_tab(self):
        bar = TabBar()
        bar.update_tabs([TabInfo(tab_id="main", label="Main", is_active=True)])
        rendered = bar.render()
        assert "×" not in rendered.plain
        assert bar._close_spans == []

    def test_render_no_close_marker_for_busy_tab(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="Main", is_active=True),
                TabInfo(tab_id="tab-1", label="Busy", is_active=False, is_busy=True),
            ]
        )
        rendered = bar.render()
        assert rendered.plain.count("×") == 1
        assert [tab_id for tab_id, _start, _end in bar._close_spans] == ["main"]

    def test_render_empty_tabs(self):
        bar = TabBar()
        bar.update_tabs([])
        rendered = bar.render()
        assert "⍬" in rendered.plain

    def test_render_fallback_to_tab_id(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="tab-42", label="", is_active=True),
            ]
        )
        rendered = bar.render()
        assert "tab-42" in rendered.plain

    def test_set_leading_symbol(self):
        bar = TabBar()
        bar.set_leading_symbol("⌬")
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="Test", is_active=True),
            ]
        )
        rendered = bar.render()
        assert "⌬" in rendered.plain

    def test_active_tab_has_reverse_style(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="a", label="Active", is_active=True),
                TabInfo(tab_id="b", label="Inactive", is_active=False),
            ]
        )
        rendered = bar.render()
        style_strings = [str(s.style) for s in rendered._spans]
        assert any("reverse" in s for s in style_strings)

    def test_cjk_label_spans_use_cell_width(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(tab_id="a", label="策略", is_active=True),
                TabInfo(tab_id="b", label="Chat", is_active=False),
            ]
        )
        bar.render()
        assert len(bar._tab_spans) == 2
        a_id, a_start, a_end = bar._tab_spans[0]
        b_id, b_start, b_end = bar._tab_spans[1]
        assert a_id == "a"
        assert b_id == "b"
        assert a_end > a_start
        assert b_start >= a_end
        assert _cell_width(" 策略 ") == a_end - a_start

    def test_cell_width_ascii(self):
        assert _cell_width("abc") == 3

    def test_cell_width_cjk(self):
        assert _cell_width("策略") == 4

    def test_cell_width_mixed(self):
        assert _cell_width("a策略b") == 6

    def test_crop_cells_keeps_short_label(self):
        assert _crop_cells("Short", 10) == "Short"

    def test_crop_cells_truncates_long_ascii_label(self):
        cropped = _crop_cells("abcdefghijklmnopqrstuvwxyz", 8)
        assert cropped == "abcdefg…"
        assert _cell_width(cropped) == 8

    def test_crop_cells_truncates_long_cjk_label_on_cell_boundary(self):
        cropped = _crop_cells("策略分析上下文隔离恢复", 9)
        assert cropped.endswith("…")
        assert _cell_width(cropped) <= 9

    def test_long_labels_render_single_line_with_markers(self):
        bar = TabBar()
        bar.update_tabs(
            [
                TabInfo(
                    tab_id="main",
                    label="abcdefghijklmnopqrstuvwxyz0123456789",
                    is_active=True,
                    is_busy=True,
                    has_pending_approval=True,
                    has_unread_output=True,
                ),
                TabInfo(
                    tab_id="tab-1",
                    label="策略分析上下文隔离恢复确认",
                    is_active=False,
                    is_dirty=True,
                ),
            ]
        )
        rendered = bar.render().plain
        assert "\n" not in rendered
        assert "●!*" in rendered
        assert "~" in rendered
        assert "…" in rendered
        rich_text = bar.render()
        assert rich_text.no_wrap is True
        assert rich_text.overflow == "ellipsis"

    def test_long_cjk_hit_spans_use_cropped_cell_width(self):
        bar = TabBar()
        label = "策略分析上下文隔离恢复确认"
        bar.update_tabs([TabInfo(tab_id="main", label=label, is_active=True)])
        bar.render()
        tab_id, start, end = bar._tab_spans[0]
        cropped = _crop_cells(label, 24)
        assert tab_id == "main"
        assert end - start == _cell_width(f" {cropped} ")

    def test_vertical_render_stacks_fixed_height_tabs(self):
        bar = TabBar(orientation="vertical")
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="Main", is_active=True),
                TabInfo(tab_id="tab-1", label="Fork", is_active=False),
            ]
        )

        rendered = bar.render()

        assert rendered.plain.count("\n") == 5
        assert bar._tab_spans == [("main", 0, 3), ("tab-1", 3, 6)]
        assert rendered.plain.splitlines() == ["▎ ", "▎1", "▎ ", "  ", " 2", "  "]
        assert "Main" not in rendered.plain
        assert "Fork" not in rendered.plain

    def test_vertical_render_centers_tabs_when_height_is_known(self):
        class SizedTabBar(TabBar):
            def _rail_height(self) -> int:
                return 20

        bar = SizedTabBar(orientation="vertical")
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="Main", is_active=True),
                TabInfo(tab_id="tab-1", label="Fork", is_active=False),
            ]
        )

        rendered = bar.render()

        assert rendered.plain.startswith("\n" * 7)
        assert bar._tab_spans == [("main", 7, 10), ("tab-1", 10, 13)]
        assert bar._tab_spans[1][1] <= 11 < bar._tab_spans[1][2]

    def test_vertical_render_uses_alternating_tab_backgrounds(self):
        bar = TabBar(orientation="vertical")
        bar.set_rail_palette(theme_bg="#123456", text="#eeeeee", text_dim="#777777")
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="Main", is_active=True),
                TabInfo(tab_id="tab-1", label="Fork", is_active=False),
            ]
        )

        rendered = bar.render()
        style_strings = [str(span.style) for span in rendered._spans]

        assert any("#eeeeee" in style for style in style_strings)
        assert any("#777777" in style for style in style_strings)
        assert any("on #123456" in style for style in style_strings)
        assert any(f"on {_lighten_hex_color('#123456')}" in style for style in style_strings)
        assert all("on #000000" not in style for style in style_strings)

    def test_vertical_render_can_override_alternate_tab_background(self):
        bar = TabBar(orientation="vertical")
        bar.set_rail_palette(
            theme_bg="#123456",
            alternate_bg="#456789",
            text="#eeeeee",
            text_dim="#777777",
        )
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="Main", is_active=True),
                TabInfo(tab_id="tab-1", label="Fork", is_active=False),
            ]
        )

        style_strings = [str(span.style) for span in bar.render()._spans]

        assert any("on #123456" in style for style in style_strings)
        assert any("on #456789" in style for style in style_strings)

    def test_vertical_render_has_no_close_hitboxes_in_one_cell_mode(self):
        bar = TabBar(orientation="vertical")
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="Main", is_active=True),
                TabInfo(tab_id="tab-1", label="Fork", is_active=False),
                TabInfo(tab_id="tab-2", label="Busy", is_active=False, is_busy=True),
            ]
        )

        rendered = bar.render()

        assert "×" not in rendered.plain
        assert bar._close_spans == []
        assert bar._close_hitboxes == []

    def test_vertical_render_status_markers(self):
        bar = TabBar(orientation="vertical")
        bar.update_tabs(
            [
                TabInfo(
                    tab_id="main",
                    label="Main",
                    is_active=True,
                    is_busy=True,
                    has_pending_approval=True,
                    has_unread_output=True,
                ),
                TabInfo(tab_id="tab-1", label="Fork", is_dirty=True),
            ]
        )

        rendered = bar.render().plain

        assert "●" in rendered
        assert "!" not in rendered
        assert "*" not in rendered
        assert "~" in rendered

    def test_vertical_click_spans_are_y_based(self):
        bar = TabBar(orientation="vertical")
        bar.update_tabs(
            [
                TabInfo(tab_id="main", label="Main", is_active=True),
                TabInfo(tab_id="tab-1", label="Fork", is_active=False),
            ]
        )
        bar.render()

        assert bar._tab_spans[0] == ("main", 0, 3)
        assert bar._tab_spans[1] == ("tab-1", 3, 6)
        assert bar._tab_spans[1][1] <= 4 < bar._tab_spans[1][2]


if __name__ == "__main__":
    unittest.main()
