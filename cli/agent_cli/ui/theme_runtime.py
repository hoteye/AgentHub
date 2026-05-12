from __future__ import annotations

import re
from typing import Any

from rich.style import Style as RichStyle


def builtin_theme_ids(builtin_themes: dict[str, Any]) -> tuple[str, ...]:
    return tuple(builtin_themes)


def resolve_cli_theme(
    builtin_themes: dict[str, Any],
    *,
    theme_id: str | None,
    default_theme_id: str,
) -> Any:
    requested = str(theme_id or "").strip().lower()
    return builtin_themes.get(requested, builtin_themes[default_theme_id])


def build_theme_styles(theme: Any, *, theme_styles_type: type) -> Any:
    return theme_styles_type(
        user_text_style=RichStyle(color=theme.text_primary, bgcolor=theme.user_surface_bg),
        user_prefix_style=RichStyle(
            color=theme.text_muted, bgcolor=theme.user_surface_bg, bold=True, dim=True
        ),
        user_image_style=RichStyle(color=theme.accent_primary, bgcolor=theme.user_surface_bg),
        system_text_style=RichStyle(color=theme.text_muted),
        commentary_text_style=RichStyle(color=theme.text_secondary),
        commentary_prefix_style=RichStyle(color=theme.text_muted, bold=True, dim=True),
        final_text_style=RichStyle(color=theme.text_primary),
        final_prefix_style=RichStyle(color=theme.text_muted, bold=True, dim=True),
        reasoning_text_style=RichStyle(color=theme.text_muted, dim=True, italic=True),
        reasoning_prefix_style=RichStyle(color=theme.text_dim, dim=True),
        markdown_h1_style=RichStyle(bold=True, underline=True),
        markdown_h2_style=RichStyle(bold=True),
        markdown_h3_style=RichStyle(bold=True, italic=True),
        markdown_h4_style=RichStyle(italic=True),
        markdown_h5_style=RichStyle(italic=True),
        markdown_h6_style=RichStyle(italic=True),
        markdown_emphasis_style=RichStyle(italic=True),
        markdown_strong_style=RichStyle(bold=True),
        markdown_code_style=RichStyle(color=theme.markdown_code),
        markdown_link_style=RichStyle(color=theme.markdown_link, underline=True),
        markdown_blockquote_style=RichStyle(color=theme.markdown_blockquote),
        markdown_ordered_list_marker_style=RichStyle(color=theme.markdown_ordered_marker),
        markdown_syntax_comment_style=RichStyle(color=theme.syntax_comment, italic=True),
        markdown_syntax_keyword_style=RichStyle(color=theme.syntax_keyword),
        markdown_syntax_string_style=RichStyle(color=theme.syntax_string),
        markdown_syntax_number_style=RichStyle(color=theme.syntax_number),
        markdown_syntax_operator_style=RichStyle(color=theme.syntax_operator),
        markdown_syntax_name_style=RichStyle(color=theme.syntax_name),
        markdown_syntax_builtin_style=RichStyle(color=theme.syntax_builtin),
        activity_text_style=RichStyle(color=theme.text_secondary),
        activity_prefix_style=RichStyle(color=theme.text_muted, bold=True, dim=True),
        activity_detail_style=RichStyle(color=theme.text_muted),
        web_text_style=RichStyle(color=theme.accent_primary_soft),
        error_text_style=RichStyle(color=theme.error, bold=True),
        error_detail_style=RichStyle(color=theme.error_soft),
        separator_text_style=RichStyle(color=theme.text_dim, dim=True),
        tree_prefix_style=RichStyle(color=theme.text_dim),
        completion_time_style=RichStyle(
            color=theme.text_primary,
            bgcolor=_darken_hex_color(theme.info_surface_bg, factor=0.82),
            dim=True,
        ),
    )


_HEX_COLOR_RE = re.compile(r"^#(?P<rgb>[0-9a-fA-F]{6})$")


def _hex_channels(color: str) -> tuple[int, int, int] | None:
    candidate = str(color or "").strip()
    matched = _HEX_COLOR_RE.match(candidate)
    if not matched:
        return None
    rgb = matched.group("rgb")
    return tuple(int(rgb[idx : idx + 2], 16) for idx in (0, 2, 4))


def _darken_hex_color(color: str, *, factor: float) -> str:
    channels = _hex_channels(color)
    if channels is None:
        return str(color or "").strip()
    darkened = [max(0, min(255, int(channel * factor))) for channel in channels]
    return "#{:02x}{:02x}{:02x}".format(*darkened)


def _blend_hex_colors(base: str, tint: str, *, ratio: float) -> str:
    base_channels = _hex_channels(base)
    tint_channels = _hex_channels(tint)
    if base_channels is None or tint_channels is None:
        return str(tint or base or "").strip()
    normalized = max(0.0, min(1.0, float(ratio)))
    blended = [
        max(0, min(255, int(round((1.0 - normalized) * left + normalized * right))))
        for left, right in zip(base_channels, tint_channels, strict=False)
    ]
    return "#{:02x}{:02x}{:02x}".format(*blended)


def scrollbar_palette(theme: Any) -> dict[str, str]:
    track = _blend_hex_colors(theme.panel_bg, theme.info_surface_bg, ratio=0.55)
    thumb = _blend_hex_colors(track, theme.accent_primary, ratio=0.28)
    thumb_hover = _blend_hex_colors(track, theme.accent_primary, ratio=0.42)
    thumb_active = _blend_hex_colors(track, theme.accent_primary, ratio=0.58)
    return {
        "track": track,
        "track_hover": track,
        "track_active": track,
        "thumb": thumb,
        "thumb_hover": thumb_hover,
        "thumb_active": thumb_active,
        "corner": track,
    }


def build_app_css(theme: Any) -> str:
    scrollbar = scrollbar_palette(theme)
    return f"""
    Screen {{
        layout: vertical;
        background: {theme.app_bg};
        color: {theme.text_secondary};
    }}

    #body {{
        height: 1fr;
        layout: horizontal;
        margin: 0;
    }}

    #top_title_row {{
        height: 1;
        layout: horizontal;
        background: {theme.info_surface_bg};
    }}

    #top_title_icon {{
        width: 2;
        color: {theme.text_secondary};
        background: {theme.info_surface_bg};
        text-align: center;
        content-align: center middle;
        padding: 0;
    }}

    #top_title_bar {{
        width: 1fr;
        padding: 0 1;
        background: {theme.info_surface_bg};
        color: {theme.text_secondary};
        text-align: center;
    }}

    #work_area {{
        width: 1fr;
        height: 1fr;
        layout: vertical;
        margin: 0;
    }}

    #tab_bar {{
        width: 2;
        height: 1fr;
        padding: 0;
        content-align: left top;
        color: {theme.text_secondary};
    }}

    #main_log, #transcript_log {{
        height: 1fr;
        border: none;
        background: {theme.panel_bg};
        padding: 0;
        scrollbar-background: {scrollbar['track']};
        scrollbar-background-hover: {scrollbar['track_hover']};
        scrollbar-background-active: {scrollbar['track_active']};
        scrollbar-color: {scrollbar['thumb']};
        scrollbar-color-hover: {scrollbar['thumb_hover']};
        scrollbar-color-active: {scrollbar['thumb_active']};
        scrollbar-corner-color: {scrollbar['corner']};
    }}

    #bottom_dock {{
        dock: bottom;
        height: 3;
        margin: 0;
        padding: 0;
        background: {theme.app_bg};
    }}

    #slash_popup {{
        height: auto;
        margin: 0 0 1 0;
        padding: 0;
        background: {theme.overlay_bg};
        color: {theme.text_secondary};
        display: none;
    }}

    #status_line {{
        height: 1;
        color: {theme.text_dim};
        padding: 0;
        background: {theme.info_surface_bg};
    }}

    #composer_shell {{
        height: 1;
        margin-bottom: 0;
        padding: 0;
        background: {theme.user_surface_bg};
    }}

    #composer_footer {{
        height: 1;
        border: none;
        background: {theme.info_surface_bg};
        color: {theme.text_dim};
        padding: 0;
    }}

    #prompt_composer {{
        height: 1;
        margin-bottom: 0;
        border: none;
        background: {theme.user_surface_bg};
        color: {theme.text_primary};
        padding: 0;
    }}
    """
