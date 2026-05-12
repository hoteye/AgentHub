from __future__ import annotations

import re

from textual.widgets import Static

from cli.agent_cli.ui.composer_helpers import (
    ComposerActionMixin,
    ComposerCursorMixin,
    ComposerEditMixin,
    ComposerRenderMixin,
    ComposerRuntimeMixin,
    ComposerSelectionMixin,
    ComposerSnapshot,
    ComposerWidgetMixin,
)
from cli.agent_cli.ui.presentation import MessageCatalog, PresentationSettings, default_messages
from cli.agent_cli.ui.theme import CliTheme, default_theme
from cli.agent_cli.ui.theme import TRANSCRIPT_USER_PREFIX


class PromptComposer(
    ComposerSelectionMixin,
    ComposerCursorMixin,
    ComposerEditMixin,
    ComposerWidgetMixin,
    ComposerRenderMixin,
    ComposerActionMixin,
    ComposerRuntimeMixin,
    Static,
):
    can_focus = True
    MAX_VISIBLE_LINES = 6
    PROMPT_PREFIX = TRANSCRIPT_USER_PREFIX
    PLACEHOLDER_TEXT = "Ask AgentHub to do anything"
    CURSOR_GLYPH = " "
    CURSOR_TOKEN = "\0"
    WORD_SEPARATORS = "`~!@#$%^&*()-=+[{]}\\|;:'\",.<>/?"
    PASTE_BURST_GAP_SECONDS = 0.02
    PASTE_BURST_FLUSH_SECONDS = 0.035
    RIGHT_CLICK_PASTE_SUPPRESS_SECONDS = 0.4
    ALT_ENTER_ESCAPE_FALLBACK_SECONDS = 0.25
    MULTI_CLICK_TIMEOUT_SECONDS = 0.4
    ATTACHMENT_REFERENCE_RE = re.compile(r"(?<!\S)@(?:\"[^\"]+\"|'[^']+'|\S+)")
    PASTED_PLACEHOLDER_RE = re.compile(r"\[Pasted Content \d+ chars(?: #\d+)?\]")
    IMAGE_ATTACHMENT_EXTENSIONS = {
        "apng",
        "avif",
        "bmp",
        "gif",
        "heic",
        "heif",
        "jpeg",
        "jpg",
        "png",
        "svg",
        "tif",
        "tiff",
        "webp",
    }

    def __init__(
        self,
        text: str = "",
        *,
        presentation: PresentationSettings | None = None,
        theme: CliTheme | None = None,
        messages: MessageCatalog | None = None,
        **kwargs,
    ) -> None:
        super().__init__("", **kwargs)
        self._theme = theme or (presentation.theme if presentation is not None else default_theme())
        self._messages = messages or (presentation.messages if presentation is not None else default_messages())
        self._text = text
        self._cursor_pos = len(text)
        self._selection_anchor: int | None = None
        self._preferred_column: int | None = None
        self._last_render_width = 0
        self._drag_anchor_pos: int | None = None
        self._is_drag_selecting = False
        self._undo_stack: list[ComposerSnapshot] = []
        self._redo_stack: list[ComposerSnapshot] = []
        self._last_click_at = 0.0
        self._last_click_cell: tuple[int, int] | None = None
        self._click_streak = 0
        self._pending_ascii_char = ""
        self._pending_ascii_at = 0.0
        self._paste_burst_buffer = ""
        self._paste_burst_last_at = 0.0
        self._pending_alt_enter_escape_token = 0
        self._pending_alt_enter_escape_active_token = 0
        self._suppress_paste_until = 0.0
        self._suppress_paste_text: str | None = None
        self._sync()

    def _placeholder_text(self) -> str:
        return self._messages.text("composer.placeholder") or self.PLACEHOLDER_TEXT

    def set_presentation(
        self,
        *,
        presentation: PresentationSettings | None = None,
        theme: CliTheme | None = None,
        messages: MessageCatalog | None = None,
    ) -> None:
        self._theme = theme or (presentation.theme if presentation is not None else self._theme)
        self._messages = messages or (presentation.messages if presentation is not None else self._messages)
        self.refresh(repaint=True, layout=False)
