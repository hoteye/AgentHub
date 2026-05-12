from __future__ import annotations

from rich.text import Text


def popup_scroll_top(*, item_count: int, selected_index: int, visible: int, current_scroll_top: int) -> int:
    if item_count <= 0 or visible <= 0:
        return 0
    scroll_top = int(current_scroll_top)
    if selected_index < scroll_top:
        scroll_top = selected_index
    elif selected_index >= scroll_top + visible:
        scroll_top = selected_index + 1 - visible
    max_scroll = max(0, item_count - visible)
    return max(0, min(scroll_top, max_scroll))


def highlighted_text(value: str, *, query: str, style: str, highlight_style: str) -> Text:
    text = Text(style=style, end="")
    if not query:
        text.append(value, style=style)
        return text
    lower_value = value.lower()
    cursor = 0
    while cursor < len(value):
        hit = lower_value.find(query, cursor)
        if hit < 0:
            text.append(value[cursor:], style=style)
            break
        if hit > cursor:
            text.append(value[cursor:hit], style=style)
        text.append(value[hit : hit + len(query)], style=highlight_style)
        cursor = hit + len(query)
    return text


def render_popup(
    *,
    theme: object,
    items: list[dict[str, str]],
    selected_index: int,
    scroll_top: int,
    visible: int,
    highlighted_text_fn,
) -> Text:
    renderable = Text(no_wrap=True, overflow="crop", end="")
    visible_items = items[scroll_top : scroll_top + visible]
    for row_index, item in enumerate(visible_items):
        index = scroll_top + row_index
        selected = index == selected_index
        disabled = str(item.get("disabled") or "").strip().lower() in {"1", "true", "yes", "on"}
        prefix = "› " if selected else "  "
        if disabled and selected:
            line_style = f"reverse {theme.selection_bg} dim"
        elif selected:
            line_style = f"reverse {theme.selection_bg}"
        else:
            line_style = theme.text_dim if disabled else theme.text_primary
        usage = str(item.get("usage") or item.get("path") or f"/{item.get('name') or ''}")
        description = str(item.get("description") or "").strip()
        disabled_reason = str(item.get("disabled_reason") or "").strip()
        if disabled_reason:
            description = f"{description}  {disabled_reason}".strip()
        renderable.append(prefix, style=theme.accent_primary if selected else theme.text_dim)
        renderable.append(
            highlighted_text_fn(
                usage,
                style=line_style,
                highlight_style=f"bold {theme.text_primary}",
            )
        )
        if description:
            renderable.append("  ", style=line_style)
            description_style = (
                f"reverse {theme.selection_bg} dim"
                if selected and disabled
                else (theme.text_dim if disabled else (theme.text_muted if not selected else f"reverse {theme.selection_bg}"))
            )
            renderable.append(
                highlighted_text_fn(
                    description,
                    style=description_style,
                    highlight_style=(
                        (f"bold {theme.text_dim}" if disabled else f"bold {theme.accent_warning}")
                        if not selected
                        else (f"reverse bold {theme.text_dim}" if disabled else f"reverse bold {theme.text_primary}")
                    ),
                )
            )
        if row_index < len(visible_items) - 1:
            renderable.append("\n")
    return renderable
