from __future__ import annotations

from unittest.mock import patch

import pytest
from textual.document._document import Selection

from cli.agent_cli.ui import unicode_word_break_runtime
from cli.agent_cli.ui.transcript_selection_range_runtime import select_word_at


class _FakeArea:
    WORD_SEPARATORS = "`~!@#$%^&*()-=+[{]}\\|;:'\",.<>/?"

    def __init__(self, line: str) -> None:
        self.document = [line]
        self.selection = Selection.cursor((0, 0))

    @classmethod
    def _is_word_separator(cls, char: str) -> bool:
        return char in cls.WORD_SEPARATORS


def _selected_text(area: _FakeArea) -> str:
    (start_row, start_column), (end_row, end_column) = sorted((area.selection.start, area.selection.end))
    assert start_row == end_row == 0
    return area.document[0][start_column:end_column]


def test_select_word_at_prefers_unicode_word_break_range() -> None:
    area = _FakeArea("中文English混排")
    column = area.document[0].index("g")

    with patch(
        "cli.agent_cli.ui.transcript_selection_range_runtime.unicode_word_break_runtime.word_range_at",
        return_value=(2, 9),
    ):
        select_word_at(area, 0, column)

    assert _selected_text(area) == "English"


def test_select_word_at_falls_back_when_unicode_word_break_unavailable() -> None:
    area = _FakeArea("foo-bar")
    column = area.document[0].index("b")

    with patch(
        "cli.agent_cli.ui.transcript_selection_range_runtime.unicode_word_break_runtime.word_range_at",
        return_value=None,
    ):
        select_word_at(area, 0, column)

    assert _selected_text(area) == "bar"


@pytest.mark.skipif(
    unicode_word_break_runtime.word_range_at("中文测试", 0) is None,
    reason="ICU word break runtime not available",
)
def test_icu_word_range_at_handles_chinese_mixed_text() -> None:
    text = "中文English混排"

    assert unicode_word_break_runtime.word_range_at(text, text.index("文")) == (0, 2)
    assert unicode_word_break_runtime.word_range_at(text, text.index("g")) == (2, 9)
    assert unicode_word_break_runtime.word_range_at(text, text.index("混")) == (9, 10)


@pytest.mark.skipif(
    unicode_word_break_runtime.word_range_at("中文测试", 0) is None,
    reason="ICU word break runtime not available",
)
def test_icu_word_range_at_keeps_chinese_punctuation_separate() -> None:
    text = "这是中文，测试一下。"

    assert unicode_word_break_runtime.word_range_at(text, text.index("文")) == (2, 4)
    assert unicode_word_break_runtime.word_range_at(text, text.index("，")) == (4, 5)
    assert unicode_word_break_runtime.word_range_at(text, text.index("测")) == (5, 7)
