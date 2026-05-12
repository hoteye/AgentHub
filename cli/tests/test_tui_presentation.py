from __future__ import annotations

import tomllib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest.mock import patch

from rich.cells import cell_len
from textual.color import Color
from textual.widgets import Static

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.ui.approval_modal import ApprovalOverlay
from cli.agent_cli.ui.composer import PromptComposer
from cli.agent_cli.ui.presentation import (
    detect_system_locale,
    project_presentation_override_path,
    resolve_presentation_settings,
    save_user_presentation_preferences,
)
from cli.agent_cli.ui.request_user_input_modal import RequestUserInputOverlay
from cli.agent_cli.ui.runtime_bridge import FallbackRuntime
from cli.agent_cli.ui.status_indicator import build_status_indicator_text
from cli.agent_cli.ui.theme import build_app_css, builtin_theme_ids, resolve_cli_theme
from cli.agent_cli.ui.theme_runtime import scrollbar_palette

_IDLE_CAT_FRAMES = {"~=(^.^)=3", "3=(^.^)=~"}


class PresentationResolverTest(unittest.TestCase):
    def test_builtin_theme_catalog_includes_harbor_mist(self) -> None:
        self.assertEqual(
            builtin_theme_ids(), ("reference_dark", "neutral_dark", "harbor_mist", "light")
        )

    def test_dark_theme_palettes_are_visibly_distinct(self) -> None:
        reference = resolve_cli_theme("reference_dark")
        neutral = resolve_cli_theme("neutral_dark")

        self.assertNotEqual(reference.panel_bg, neutral.panel_bg)
        self.assertNotEqual(reference.accent_primary, neutral.accent_primary)

    def test_harbor_mist_uses_soft_blue_input_rail_palette(self) -> None:
        harbor = resolve_cli_theme("harbor_mist")

        self.assertEqual(harbor.app_bg, "#0d1117")
        self.assertEqual(harbor.panel_bg, "#0d1117")
        self.assertEqual(harbor.info_surface_bg, "#2a4359")
        self.assertEqual(harbor.user_surface_bg, "#34516a")

    def test_theme_css_includes_request_user_input_overlay_selector(self) -> None:
        css = build_app_css(resolve_cli_theme("reference_dark"))
        self.assertIn(f"#{RequestUserInputOverlay.ROOT_ID}", css)
        self.assertIn("layer: overlay;", css)

    def test_theme_css_includes_approval_overlay_selector(self) -> None:
        css = build_app_css(resolve_cli_theme("reference_dark"))
        self.assertIn(f"#{ApprovalOverlay.ROOT_ID}", css)
        self.assertIn("layer: overlay;", css)

    def test_theme_css_includes_theme_aware_scrollbar_palette(self) -> None:
        theme = resolve_cli_theme("harbor_mist")
        css = build_app_css(theme)
        palette = scrollbar_palette(theme)

        self.assertIn(f"scrollbar-background: {palette['track']};", css)
        self.assertIn(f"scrollbar-color: {palette['thumb']};", css)
        self.assertIn(f"scrollbar-color-hover: {palette['thumb_hover']};", css)
        self.assertIn(f"scrollbar-color-active: {palette['thumb_active']};", css)

    def test_theme_css_uses_edge_to_edge_padding_for_lower_sections(self) -> None:
        css = build_app_css(resolve_cli_theme("reference_dark"))
        self.assertRegex(css, r"#main_log,\s*#transcript_log\s*\{[^}]*padding:\s*0;")
        self.assertRegex(css, r"#bottom_dock\s*\{[^}]*padding:\s*0;")
        self.assertRegex(css, r"#prompt_composer\s*\{[^}]*padding:\s*0;")

    def test_detect_system_locale_normalizes_supported_values(self) -> None:
        self.assertEqual(detect_system_locale(env={"LANG": "zh_CN.UTF-8"}), "zh-CN")
        self.assertEqual(detect_system_locale(env={"LANG": "ja_JP.UTF-8"}), "ja")
        self.assertEqual(detect_system_locale(env={"LANG": "fr_FR.UTF-8"}), "fr")

    def test_resolve_presentation_settings_reads_cli_block_from_project_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.toml").write_text(
                '[cli]\nlang = "fr"\n\n[cli.theme]\nid = "light"\n',
                encoding="utf-8",
            )

            presentation = resolve_presentation_settings(cwd=root)

            self.assertEqual(presentation.locale, "fr")
            self.assertEqual(presentation.theme_id, "light")
            self.assertFalse(presentation.idle_cat_enabled)

    def test_resolve_presentation_settings_reads_idle_cat_flag_from_monorepo_cli_config(
        self,
    ) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "cli" / ".config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.toml").write_text(
                "[cli]\nidle_cat = true\n",
                encoding="utf-8",
            )

            presentation = resolve_presentation_settings(cwd=root)

            self.assertTrue(presentation.idle_cat_enabled)

    def test_cli_arguments_override_project_presentation_settings(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.toml").write_text(
                '[cli]\nlang = "fr"\n\n[cli.theme]\nid = "light"\n',
                encoding="utf-8",
            )

            presentation = resolve_presentation_settings(
                cwd=root,
                lang="zh-CN",
                theme_id="neutral_dark",
            )

            self.assertEqual(presentation.locale, "zh-CN")
            self.assertEqual(presentation.theme_id, "neutral_dark")

    def test_save_user_presentation_preferences_updates_shared_config_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            legacy = Path(tmpdir) / "legacy"
            config_path = home / "config.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                '[notice]\nhide = true\n\n[cli.theme]\nid = "light"\n', encoding="utf-8"
            )

            with (
                patch("cli.agent_cli.ui.presentation.AGENT_CLI_HOME", home),
                patch("cli.agent_cli.ui.presentation.LEGACY_COMPAT_HOME", legacy),
            ):
                saved_path = save_user_presentation_preferences(lang="ja", theme_id="harbor_mist")

            self.assertEqual(saved_path, config_path)
            parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(parsed["cli"]["lang"], "ja")
            self.assertEqual(parsed["cli"]["theme"]["id"], "harbor_mist")
            self.assertTrue(parsed["notice"]["hide"])

    def test_project_presentation_override_path_prefers_nearest_project_layer(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = root / "workspace" / "nested"
            (root / ".config").mkdir(parents=True, exist_ok=True)
            (root / ".config" / "config.toml").write_text('[cli]\nlang = "fr"\n', encoding="utf-8")
            (root / "workspace" / ".config").mkdir(parents=True, exist_ok=True)
            (root / "workspace" / ".config" / "config.toml").write_text(
                '[cli.theme]\nid = "light"\n',
                encoding="utf-8",
            )
            workspace.mkdir(parents=True, exist_ok=True)

            lang_path = project_presentation_override_path(cwd=workspace, setting="lang")
            theme_path = project_presentation_override_path(cwd=workspace, setting="theme")

            self.assertEqual(lang_path, root / ".config" / "config.toml")
            self.assertEqual(theme_path, root / "workspace" / ".config" / "config.toml")


class PresentationUiSmokeTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _static_plain(widget: Static) -> str:
        renderable = getattr(widget, "renderable", None)
        if renderable is not None:
            return getattr(renderable, "plain", str(renderable))
        rendered = widget.render()
        if hasattr(rendered, "renderable"):
            inner = rendered.renderable
            return getattr(inner, "plain", str(inner))
        return getattr(rendered, "plain", str(rendered))

    async def test_app_uses_selected_theme_and_locale_for_phase1_chrome(self) -> None:
        app = AgentCliApp(language="zh-CN", theme_id="light")

        async with app.run_test() as pilot:
            await pilot.pause()

            footer = app.query_one("#composer_footer", Static)
            status_line = app.query_one("#status_line", Static)
            composer = app.query_one("#prompt_composer", PromptComposer)

            self.assertEqual(footer.styles.background, Color.parse(app._theme.info_surface_bg))
            self.assertEqual(status_line.styles.background, Color.parse(app._theme.info_surface_bg))
            self.assertNotIn("查看快捷键", self._static_plain(status_line))
            self.assertNotIn("剩余上下文 100%", self._static_plain(footer))
            self.assertIn("anthropic", self._static_plain(footer))
            self.assertIn(
                "让 AgentHub 处理任何事情", composer.build_render_text(80, focused=False).plain
            )

            app._idle_status_started_at = monotonic() - app.IDLE_STATUS_DELAY_SECONDS - 1.0
            app._refresh_dynamic_hint()
            await pilot.pause()

            self.assertNotIn("查看快捷键", self._static_plain(status_line))

            app._set_busy(True)
            await pilot.pause()

            self.assertIn("处理中", self._static_plain(status_line))

    async def test_footer_context_usage_with_window_shows_remaining_detail(self) -> None:
        app = AgentCliApp(language="zh-CN", theme_id="light")

        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause()
            app._update_status(
                {
                    "context_window_used_tokens": "123456",
                    "model_context_window": "200000",
                }
            )
            await pilot.pause()

            footer = app.query_one("#composer_footer", Static)
            rendered = self._static_plain(footer)

            self.assertIn("剩余上下文 41% · 123k/200k", rendered)
            self.assertNotIn("123k 已用上下文", rendered)

    async def test_footer_context_usage_without_window_keeps_token_count_visible(self) -> None:
        app = AgentCliApp(language="zh-CN", theme_id="light")

        async with app.run_test(size=(12, 20)) as pilot:
            await pilot.pause()
            app._update_status({"context_window_used_tokens": "123456"})
            await pilot.pause()

            footer = app.query_one("#composer_footer", Static)
            rendered = self._static_plain(footer)

            self.assertIn("123k", rendered)
            self.assertNotIn("已用上下", rendered)

    async def test_footer_overflow_keeps_right_context_and_truncates_left_shortcuts(self) -> None:
        app = AgentCliApp(language="zh-CN", theme_id="light")

        async with app.run_test() as pilot:
            await pilot.pause()

            left = f"  {app._t('footer.shortcuts')}"
            app._update_status(
                {
                    "context_window_used_tokens": "123456",
                    "model_context_window": "200000",
                }
            )
            await pilot.pause()
            right = app._t("footer.context_left.detail", percent=41, used="123k", window="200k")
            content_width = max(1, cell_len(left) + cell_len(right) - 1)

            await pilot.resize_terminal(content_width, 24)
            await pilot.pause()

            footer = app.query_one("#composer_footer", Static)
            rendered = self._static_plain(footer)

            self.assertIn(right, rendered)
            self.assertNotIn(left, rendered)
            self.assertLessEqual(cell_len(rendered), content_width)

    async def test_app_shows_idle_cat_when_enabled_in_cli_subproject_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "cli" / ".config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.toml").write_text("[cli]\nidle_cat = true\n", encoding="utf-8")

            runtime = FallbackRuntime()
            runtime.cwd = root
            app = AgentCliApp(runtime=runtime, language="zh-CN", theme_id="light")

            async with app.run_test() as pilot:
                await pilot.pause()

                status_line = app.query_one("#status_line", Static)

                self.assertEqual(self._static_plain(status_line), "")

                app._idle_status_started_at = monotonic() - app.IDLE_STATUS_DELAY_SECONDS - 1.0
                app._refresh_dynamic_hint()
                await pilot.pause()

                self.assertIn(self._static_plain(status_line).strip(), _IDLE_CAT_FRAMES)

    def test_status_indicator_localizes_interrupt_hint(self) -> None:
        presentation = resolve_presentation_settings(lang="fr")

        rendered = build_status_indicator_text(
            "",
            width=80,
            started_at=100.0,
            now=101.0,
            theme=presentation.theme,
            messages=presentation.messages,
        )

        self.assertIn("esc pour interrompre", rendered.plain)
