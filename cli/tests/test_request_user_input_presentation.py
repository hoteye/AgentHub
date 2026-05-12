from __future__ import annotations

import unittest

from cli.agent_cli.ui.presentation import SUPPORTED_LOCALES, resolve_presentation_settings
from cli.agent_cli.ui.request_user_input_modal import RequestUserInputOverlay
from cli.agent_cli.ui.theme import build_app_css, builtin_theme_ids, resolve_cli_theme


class RequestUserInputPresentationContractTest(unittest.TestCase):
    _RUI_KEYS: tuple[tuple[str, dict[str, object]], ...] = (
        ("rui.title", {}),
        ("rui.question_progress", {"current": 1, "total": 3}),
        ("rui.other_prefix", {}),
        ("rui.other_placeholder", {}),
        ("rui.help_line_question", {}),
        ("rui.review_title", {}),
        ("rui.review_subtitle", {}),
        ("rui.help_line_review", {}),
        ("rui.notice_missing_answers", {}),
    )

    def test_rui_message_keys_are_available_for_supported_locales(self) -> None:
        for locale in SUPPORTED_LOCALES:
            with self.subTest(locale=locale):
                catalog = resolve_presentation_settings(lang=locale).messages
                for key, kwargs in self._RUI_KEYS:
                    with self.subTest(locale=locale, key=key):
                        text = catalog.text(key, **kwargs)
                        self.assertTrue(text.strip())

    def test_overlay_css_selector_exists_for_all_builtin_themes(self) -> None:
        selector = f"#{RequestUserInputOverlay.ROOT_ID}"
        for theme_id in builtin_theme_ids():
            with self.subTest(theme_id=theme_id):
                css = build_app_css(resolve_cli_theme(theme_id))
                self.assertIn(selector, css)
                self.assertIn("layer: overlay;", css)

