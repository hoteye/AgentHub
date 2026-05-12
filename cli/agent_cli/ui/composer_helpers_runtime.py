from __future__ import annotations

from rich.text import Text

from cli.agent_cli.ui import composer_render_runtime, composer_widget_runtime


class ComposerRenderMixinRuntime:
    @classmethod
    def _prompt_prefix(cls, width: int) -> str:
        return composer_render_runtime.prompt_prefix(cls, width)

    @classmethod
    def _continuation_prefix(cls, width: int) -> str:
        return composer_render_runtime.continuation_prefix(cls, width)

    @classmethod
    def _display_width(cls, value: str) -> int:
        return composer_render_runtime.display_width(cls, value)

    @classmethod
    def _line_segments(cls, raw_line: str) -> list[str]:
        return composer_render_runtime.line_segments(cls, raw_line)

    @classmethod
    def _visual_lines(
        cls,
        text: str,
        cursor_pos: int,
        width: int,
        *,
        include_cursor: bool = True,
    ) -> list[str]:
        return composer_render_runtime.visual_lines(
            cls,
            text,
            cursor_pos,
            width,
            include_cursor=include_cursor,
        )

    def build_render_text(self, width: int, *, focused: bool | None = None) -> Text:
        return composer_render_runtime.build_render_text(self, width, focused=focused)

    @classmethod
    def _display_text_and_cursor(cls, text: str, cursor_pos: int) -> tuple[str, int]:
        return composer_render_runtime.display_text_and_cursor(cls, text, cursor_pos)

    @classmethod
    def _is_image_attachment_reference(cls, token: str) -> bool:
        return composer_render_runtime.is_image_attachment_reference(cls, token)

    def render(self) -> Text:
        width = composer_widget_runtime.render_width(self)
        return self.build_render_text(width, focused=self.has_focus)
