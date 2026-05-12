from __future__ import annotations

from typing import Any

from cli.agent_cli.debug_timeline import append_debug_jsonl, timeline_debug_enabled
from cli.agent_cli.ui import widgets_runtime


def log_quote_lines(
    widget: Any,
    *,
    stage: str,
    lines: list[str],
    module_file: str,
) -> None:
    if not timeline_debug_enabled():
        return
    quote_lines = widgets_runtime.quote_line_debug_entries(
        lines=lines,
        line_styles=widget._line_styles,
        serialize_style_fn=widgets_runtime.serialize_rich_style,
    )
    if not quote_lines:
        return
    append_debug_jsonl(
        "tui_render_debug.jsonl",
        stage=stage,
        module_file=module_file,
        show_cursor=bool(widget.show_cursor),
        highlight_cursor_line=bool(widget.highlight_cursor_line),
        language=str(getattr(widget, "language", None)),
        theme=str(getattr(widget, "theme", None)),
        highlight_query=bool(getattr(widget, "_highlight_query", None)),
        rich_style=widgets_runtime.serialize_rich_style(widget.rich_style),
        visual_style=widgets_runtime.serialize_rich_style(widget.visual_style.rich_style),
        quote_lines=quote_lines,
    )

