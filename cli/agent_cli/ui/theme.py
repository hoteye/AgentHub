from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from rich.style import Style as RichStyle

from cli.agent_cli.ui import theme_runtime

DEFAULT_THEME_ID = "reference_dark"


@dataclass(frozen=True, slots=True)
class CliTheme:
    id: str
    app_bg: str
    panel_bg: str
    surface_bg: str
    surface_elevated_bg: str
    overlay_bg: str
    selection_bg: str
    user_surface_bg: str
    info_surface_bg: str
    text_primary: str
    text_secondary: str
    text_muted: str
    text_dim: str
    accent_primary: str
    accent_primary_soft: str
    accent_success: str
    accent_warning: str
    markdown_code: str
    markdown_link: str
    markdown_blockquote: str
    markdown_ordered_marker: str
    syntax_comment: str
    syntax_keyword: str
    syntax_string: str
    syntax_number: str
    syntax_operator: str
    syntax_name: str
    syntax_builtin: str
    error: str
    error_soft: str
    transcript_user_prefix: str = "› "
    transcript_message_prefix: str = "• "
    transcript_continuation_prefix: str = "  "


@dataclass(frozen=True, slots=True)
class ThemeStyles:
    user_text_style: RichStyle
    user_prefix_style: RichStyle
    user_image_style: RichStyle
    system_text_style: RichStyle
    commentary_text_style: RichStyle
    commentary_prefix_style: RichStyle
    final_text_style: RichStyle
    final_prefix_style: RichStyle
    reasoning_text_style: RichStyle
    reasoning_prefix_style: RichStyle
    markdown_h1_style: RichStyle
    markdown_h2_style: RichStyle
    markdown_h3_style: RichStyle
    markdown_h4_style: RichStyle
    markdown_h5_style: RichStyle
    markdown_h6_style: RichStyle
    markdown_emphasis_style: RichStyle
    markdown_strong_style: RichStyle
    markdown_code_style: RichStyle
    markdown_link_style: RichStyle
    markdown_blockquote_style: RichStyle
    markdown_ordered_list_marker_style: RichStyle
    markdown_syntax_comment_style: RichStyle
    markdown_syntax_keyword_style: RichStyle
    markdown_syntax_string_style: RichStyle
    markdown_syntax_number_style: RichStyle
    markdown_syntax_operator_style: RichStyle
    markdown_syntax_name_style: RichStyle
    markdown_syntax_builtin_style: RichStyle
    activity_text_style: RichStyle
    activity_prefix_style: RichStyle
    activity_detail_style: RichStyle
    web_text_style: RichStyle
    error_text_style: RichStyle
    error_detail_style: RichStyle
    separator_text_style: RichStyle
    tree_prefix_style: RichStyle
    completion_time_style: RichStyle


BUILTIN_THEMES: dict[str, CliTheme] = {
    "reference_dark": CliTheme(
        id="reference_dark",
        app_bg="#0d1117",
        panel_bg="#0d1117",
        surface_bg="#11161c",
        surface_elevated_bg="#161b22",
        overlay_bg="#161b22",
        selection_bg="#1f2630",
        user_surface_bg="#11161c",
        info_surface_bg="#11161c",
        text_primary="#e6edf3",
        text_secondary="#c9d1d9",
        text_muted="#8b949e",
        text_dim="#6e7681",
        accent_primary="#79c0ff",
        accent_primary_soft="#a5d6ff",
        accent_success="#8ddb8c",
        accent_warning="#d29922",
        markdown_code="cyan",
        markdown_link="cyan",
        markdown_blockquote="green",
        markdown_ordered_marker="bright_blue",
        syntax_comment="#6c7086",
        syntax_keyword="#cba6f7",
        syntax_string="#a6e3a1",
        syntax_number="#fab387",
        syntax_operator="#94e2d5",
        syntax_name="#89b4fa",
        syntax_builtin="#94e2d5",
        error="#ff7b72",
        error_soft="#ffa198",
    ),
    "neutral_dark": CliTheme(
        id="neutral_dark",
        app_bg="#12100f",
        panel_bg="#171412",
        surface_bg="#1e1a18",
        surface_elevated_bg="#26211e",
        overlay_bg="#2b2522",
        selection_bg="#3a322d",
        user_surface_bg="#1e1a18",
        info_surface_bg="#1b1715",
        text_primary="#f3ede6",
        text_secondary="#ddd4cb",
        text_muted="#ac9f93",
        text_dim="#7e7268",
        accent_primary="#d8b25f",
        accent_primary_soft="#e6c98c",
        accent_success="#98c08e",
        accent_warning="#f0a34b",
        markdown_code="#d8b25f",
        markdown_link="#d8b25f",
        markdown_blockquote="#98c08e",
        markdown_ordered_marker="#d8b25f",
        syntax_comment="#91857b",
        syntax_keyword="#d0b4ff",
        syntax_string="#bad39a",
        syntax_number="#f2b37e",
        syntax_operator="#a7cdbd",
        syntax_name="#d9c18d",
        syntax_builtin="#a7cdbd",
        error="#ef8d7d",
        error_soft="#f7c3b9",
    ),
    "harbor_mist": CliTheme(
        id="harbor_mist",
        app_bg="#0d1117",
        panel_bg="#0d1117",
        surface_bg="#172331",
        surface_elevated_bg="#223547",
        overlay_bg="#274057",
        selection_bg="#3a5d7a",
        user_surface_bg="#34516a",
        info_surface_bg="#2a4359",
        text_primary="#eef7ff",
        text_secondary="#d7e6f3",
        text_muted="#b5cadc",
        text_dim="#8ca9c1",
        accent_primary="#8dd3ff",
        accent_primary_soft="#bae8ff",
        accent_success="#8ddb8c",
        accent_warning="#d29922",
        markdown_code="#8dd3ff",
        markdown_link="#8dd3ff",
        markdown_blockquote="#8ddb8c",
        markdown_ordered_marker="#8dd3ff",
        syntax_comment="#7f95ab",
        syntax_keyword="#cba6f7",
        syntax_string="#a6e3a1",
        syntax_number="#fab387",
        syntax_operator="#94e2d5",
        syntax_name="#89b4fa",
        syntax_builtin="#94e2d5",
        error="#ff7b72",
        error_soft="#ffa198",
    ),
    "light": CliTheme(
        id="light",
        app_bg="#f4f1ea",
        panel_bg="#fbf8f2",
        surface_bg="#f8f4ed",
        surface_elevated_bg="#efe7db",
        overlay_bg="#efe7db",
        selection_bg="#d9d6cf",
        user_surface_bg="#f8f4ed",
        info_surface_bg="#f8f4ed",
        text_primary="#1f2328",
        text_secondary="#30363d",
        text_muted="#57606a",
        text_dim="#6e7781",
        accent_primary="#0a66c2",
        accent_primary_soft="#4f8fd1",
        accent_success="#1a7f37",
        accent_warning="#9a6700",
        markdown_code="#0a66c2",
        markdown_link="#0a66c2",
        markdown_blockquote="#1a7f37",
        markdown_ordered_marker="#0a66c2",
        syntax_comment="#8c959f",
        syntax_keyword="#8250df",
        syntax_string="#116329",
        syntax_number="#953800",
        syntax_operator="#0f766e",
        syntax_name="#0969da",
        syntax_builtin="#0f766e",
        error="#cf222e",
        error_soft="#ffebe9",
    ),
}


def builtin_theme_ids() -> tuple[str, ...]:
    return theme_runtime.builtin_theme_ids(BUILTIN_THEMES)


def resolve_cli_theme(theme_id: str | None) -> CliTheme:
    return theme_runtime.resolve_cli_theme(
        BUILTIN_THEMES,
        theme_id=theme_id,
        default_theme_id=DEFAULT_THEME_ID,
    )


def default_theme() -> CliTheme:
    return BUILTIN_THEMES[DEFAULT_THEME_ID]


@cache
def build_theme_styles(theme: CliTheme) -> ThemeStyles:
    return theme_runtime.build_theme_styles(
        theme,
        theme_styles_type=ThemeStyles,
    )


def build_app_css(theme: CliTheme) -> str:
    base_css = theme_runtime.build_app_css(theme)
    overlay_css = f"""
    #{'request_user_input_overlay'} {{
        layer: overlay;
        dock: top;
        width: 100%;
        height: 100%;
        background: {theme.overlay_bg} 75%;
        color: {theme.text_secondary};
        padding: 1 2;
        display: none;
    }}
    #{'approval_overlay'} {{
        layer: overlay;
        dock: bottom;
        width: 100%;
        max-height: 45%;
        height: auto;
        background: {theme.surface_elevated_bg};
        color: {theme.text_secondary};
        padding: 1 2;
        display: none;
        overflow-y: auto;
        border-top: solid {theme.accent_primary_soft};
    }}
    #{'setup_overlay'} {{
        layer: overlay;
        dock: top;
        width: 100%;
        height: 100%;
        align: center middle;
        background: {theme.overlay_bg} 75%;
        color: {theme.text_secondary};
        display: none;
    }}
    #{'setup_overlay_panel'} {{
        width: 62;
        max-width: 90%;
        background: {theme.surface_elevated_bg};
        border: round {theme.accent_primary_soft};
        padding: 1 2;
    }}
    #{'setup_overlay_title'} {{
        color: {theme.text_primary};
        text-style: bold;
        margin-bottom: 1;
    }}
    #{'setup_overlay_subtitle'} {{
        color: {theme.text_muted};
        margin-bottom: 1;
    }}
    #{'setup_provider_label'}, #{'setup_base_url_label'}, #{'setup_api_key_label'} {{
        color: {theme.text_muted};
        margin: 0;
    }}
    #{'setup_provider_select'}, #{'setup_base_url_input'}, #{'setup_api_key_input'} {{
        margin: 0;
    }}
    #{'setup_notice'} {{
        color: {theme.accent_warning};
        min-height: 1;
        margin: 0;
    }}
    #{'setup_overlay_actions'} {{
        height: auto;
        margin: 0;
    }}
    """
    return base_css + overlay_css


_DEFAULT_THEME = default_theme()
_DEFAULT_STYLES = build_theme_styles(_DEFAULT_THEME)

APP_BG = _DEFAULT_THEME.app_bg
PANEL_BG = _DEFAULT_THEME.panel_bg
SURFACE_BG = _DEFAULT_THEME.surface_bg
SURFACE_ELEVATED_BG = _DEFAULT_THEME.surface_elevated_bg
OVERLAY_BG = _DEFAULT_THEME.overlay_bg
SELECTION_BG = _DEFAULT_THEME.selection_bg
USER_SURFACE_BG = _DEFAULT_THEME.user_surface_bg
INFO_SURFACE_BG = _DEFAULT_THEME.info_surface_bg

TEXT_PRIMARY = _DEFAULT_THEME.text_primary
TEXT_SECONDARY = _DEFAULT_THEME.text_secondary
TEXT_MUTED = _DEFAULT_THEME.text_muted
TEXT_DIM = _DEFAULT_THEME.text_dim

ACCENT_CYAN = _DEFAULT_THEME.accent_primary
ACCENT_CYAN_SOFT = _DEFAULT_THEME.accent_primary_soft
ACCENT_GREEN = _DEFAULT_THEME.accent_success
ACCENT_YELLOW = _DEFAULT_THEME.accent_warning
ACCENT_CODE = _DEFAULT_THEME.markdown_code
ACCENT_LINK = _DEFAULT_THEME.markdown_link
ACCENT_BLOCKQUOTE = _DEFAULT_THEME.markdown_blockquote
ACCENT_ORDERED_MARKER = _DEFAULT_THEME.markdown_ordered_marker

SYNTAX_COMMENT = _DEFAULT_THEME.syntax_comment
SYNTAX_KEYWORD = _DEFAULT_THEME.syntax_keyword
SYNTAX_STRING = _DEFAULT_THEME.syntax_string
SYNTAX_NUMBER = _DEFAULT_THEME.syntax_number
SYNTAX_OPERATOR = _DEFAULT_THEME.syntax_operator
SYNTAX_NAME = _DEFAULT_THEME.syntax_name
SYNTAX_BUILTIN = _DEFAULT_THEME.syntax_builtin

ERROR = _DEFAULT_THEME.error
ERROR_SOFT = _DEFAULT_THEME.error_soft

TRANSCRIPT_USER_PREFIX = _DEFAULT_THEME.transcript_user_prefix
TRANSCRIPT_MESSAGE_PREFIX = _DEFAULT_THEME.transcript_message_prefix
TRANSCRIPT_CONTINUATION_PREFIX = _DEFAULT_THEME.transcript_continuation_prefix

USER_TEXT_STYLE = _DEFAULT_STYLES.user_text_style
USER_PREFIX_STYLE = _DEFAULT_STYLES.user_prefix_style
USER_IMAGE_STYLE = _DEFAULT_STYLES.user_image_style
SYSTEM_TEXT_STYLE = _DEFAULT_STYLES.system_text_style
COMMENTARY_TEXT_STYLE = _DEFAULT_STYLES.commentary_text_style
COMMENTARY_PREFIX_STYLE = _DEFAULT_STYLES.commentary_prefix_style
FINAL_TEXT_STYLE = _DEFAULT_STYLES.final_text_style
FINAL_PREFIX_STYLE = _DEFAULT_STYLES.final_prefix_style
REASONING_TEXT_STYLE = _DEFAULT_STYLES.reasoning_text_style
REASONING_PREFIX_STYLE = _DEFAULT_STYLES.reasoning_prefix_style
MARKDOWN_H1_STYLE = _DEFAULT_STYLES.markdown_h1_style
MARKDOWN_H2_STYLE = _DEFAULT_STYLES.markdown_h2_style
MARKDOWN_H3_STYLE = _DEFAULT_STYLES.markdown_h3_style
MARKDOWN_H4_STYLE = _DEFAULT_STYLES.markdown_h4_style
MARKDOWN_H5_STYLE = _DEFAULT_STYLES.markdown_h5_style
MARKDOWN_H6_STYLE = _DEFAULT_STYLES.markdown_h6_style
MARKDOWN_EMPHASIS_STYLE = _DEFAULT_STYLES.markdown_emphasis_style
MARKDOWN_STRONG_STYLE = _DEFAULT_STYLES.markdown_strong_style
MARKDOWN_CODE_STYLE = _DEFAULT_STYLES.markdown_code_style
MARKDOWN_LINK_STYLE = _DEFAULT_STYLES.markdown_link_style
MARKDOWN_BLOCKQUOTE_STYLE = _DEFAULT_STYLES.markdown_blockquote_style
MARKDOWN_ORDERED_LIST_MARKER_STYLE = _DEFAULT_STYLES.markdown_ordered_list_marker_style
MARKDOWN_SYNTAX_COMMENT_STYLE = _DEFAULT_STYLES.markdown_syntax_comment_style
MARKDOWN_SYNTAX_KEYWORD_STYLE = _DEFAULT_STYLES.markdown_syntax_keyword_style
MARKDOWN_SYNTAX_STRING_STYLE = _DEFAULT_STYLES.markdown_syntax_string_style
MARKDOWN_SYNTAX_NUMBER_STYLE = _DEFAULT_STYLES.markdown_syntax_number_style
MARKDOWN_SYNTAX_OPERATOR_STYLE = _DEFAULT_STYLES.markdown_syntax_operator_style
MARKDOWN_SYNTAX_NAME_STYLE = _DEFAULT_STYLES.markdown_syntax_name_style
MARKDOWN_SYNTAX_BUILTIN_STYLE = _DEFAULT_STYLES.markdown_syntax_builtin_style
ACTIVITY_TEXT_STYLE = _DEFAULT_STYLES.activity_text_style
ACTIVITY_PREFIX_STYLE = _DEFAULT_STYLES.activity_prefix_style
ACTIVITY_DETAIL_STYLE = _DEFAULT_STYLES.activity_detail_style
WEB_TEXT_STYLE = _DEFAULT_STYLES.web_text_style
ERROR_TEXT_STYLE = _DEFAULT_STYLES.error_text_style
ERROR_DETAIL_STYLE = _DEFAULT_STYLES.error_detail_style
SEPARATOR_TEXT_STYLE = _DEFAULT_STYLES.separator_text_style
TREE_PREFIX_STYLE = _DEFAULT_STYLES.tree_prefix_style
COMPLETION_TIME_STYLE = _DEFAULT_STYLES.completion_time_style
