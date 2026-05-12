from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from textual.color import Color

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptResponse
from cli.agent_cli.ui.tab_bar import TabBar
from cli.agent_cli.ui.theme_runtime import scrollbar_palette


class _ThemeRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "test",
                "provider_model": "test-model",
                "provider_reasoning_effort": "high",
                "provider_ready": "true",
            }

    def __init__(self) -> None:
        self.agent = self._Agent()
        self.activity_callback = None
        self.turn_event_callback = None
        self.cwd = None

    def slash_command_matches(self, query: str) -> list[dict[str, str]]:
        _ = query
        return []

    def slash_command_completion(self, query: str) -> str | None:
        _ = query
        return None

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        return PromptResponse(
            user_text=text,
            assistant_text="processed",
            attachments=list(attachments or []),
            status=self.agent.provider_status(),
            handled_as_command=False,
        )

    def interrupt_active_run(self) -> dict[str, object]:
        return {"ok": False, "interrupted": False}


class TuiThemeSwitchScrollbarTest(unittest.IsolatedAsyncioTestCase):
    async def test_theme_switch_updates_transcript_scrollbar_palette(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            root.mkdir(parents=True, exist_ok=True)
            home = Path(tmpdir) / "home"
            legacy = Path(tmpdir) / "legacy"
            runtime = _ThemeRuntime()
            runtime.cwd = root

            with (
                patch("cli.agent_cli.ui.presentation.AGENT_CLI_HOME", home),
                patch("cli.agent_cli.ui.presentation.LEGACY_COMPAT_HOME", legacy),
            ):
                app = AgentCliApp(runtime=runtime, language="en", theme_id=None)

                async with app.run_test() as pilot:
                    await pilot.pause()
                    app._set_prompt_text("/theme harbor_mist")
                    await pilot.press("enter")
                    await pilot.pause()

                    main_log = app.query_one("#main_log")
                    top_title_row = app.query_one("#top_title_row")
                    tab_bar = app.query_one("#tab_bar", TabBar)
                    palette = scrollbar_palette(app._theme)

                    self.assertEqual(app._presentation.theme_id, "harbor_mist")
                    self.assertEqual(
                        top_title_row.styles.background, Color.parse(app._theme.info_surface_bg)
                    )
                    self.assertEqual(
                        tab_bar.styles.background, Color.parse(app._theme.info_surface_bg)
                    )
                    self.assertEqual(
                        main_log.styles.scrollbar_background, Color.parse(palette["track"])
                    )
                    self.assertEqual(main_log.styles.scrollbar_color, Color.parse(palette["thumb"]))
                    self.assertEqual(
                        main_log.styles.scrollbar_color_hover, Color.parse(palette["thumb_hover"])
                    )
                    self.assertEqual(
                        main_log.styles.scrollbar_color_active, Color.parse(palette["thumb_active"])
                    )
