from __future__ import annotations

from cli.agent_cli.ui.presentation import SUPPORTED_LOCALES, resolve_presentation_settings


_REQUEST_USER_INPUT_NOTICE_KEYS: tuple[tuple[str, dict[str, object]], ...] = (
    ("rui.title", {}),
    ("rui.help_line_question", {}),
    ("rui.review_title", {}),
    ("rui.review_subtitle", {}),
    ("rui.help_line_review", {}),
    ("rui.notice_missing_answers", {}),
)


def test_request_user_input_notice_keys_available_in_non_english_locale() -> None:
    assert "zh-CN" in SUPPORTED_LOCALES

    zh_catalog = resolve_presentation_settings(lang="zh-CN").messages
    en_catalog = resolve_presentation_settings(lang="en").messages

    for key, kwargs in _REQUEST_USER_INPUT_NOTICE_KEYS:
        zh_text = zh_catalog.text(key, **kwargs)
        en_text = en_catalog.text(key, **kwargs)

        assert zh_text.strip()
        assert zh_text != key
        assert en_text.strip()


def test_request_user_input_review_and_notice_copy_not_falling_back_to_key_in_zh_cn() -> None:
    zh_catalog = resolve_presentation_settings(lang="zh-CN").messages

    review_title = zh_catalog.text("rui.review_title")
    review_subtitle = zh_catalog.text("rui.review_subtitle")
    notice_missing_answers = zh_catalog.text("rui.notice_missing_answers")

    assert review_title != "rui.review_title"
    assert review_subtitle != "rui.review_subtitle"
    assert notice_missing_answers != "rui.notice_missing_answers"
