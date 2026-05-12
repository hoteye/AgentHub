from __future__ import annotations

from rich.style import Style as RichStyle
import pytest
from textual.document._document import Selection
from textual.widgets import TextArea

from cli.agent_cli.ui import transcript_selection_runtime
from cli.agent_cli.ui.widgets import TranscriptArea


def test_transcript_area_load_transcript_skips_noop_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    original = TextArea.load_text

    def _recording_load_text(self: TextArea, text: str) -> None:
        calls.append(text)
        original(self, text)

    monkeypatch.setattr(TextArea, "load_text", _recording_load_text)

    area = TranscriptArea()
    lines = ["• hello", "  └ world"]
    line_styles = [[(0, 1, RichStyle(bold=True))], []]

    area.load_transcript(lines, line_styles=line_styles)
    area.load_transcript(list(lines), line_styles=[list(spans) for spans in line_styles])

    assert calls == ["• hello\n  └ world"]
    assert area.text == "• hello\n  └ world"


def test_transcript_area_caches_styled_base_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    original = TextArea.get_line

    def _recording_get_line(self: TextArea, line_index: int):
        calls.append(line_index)
        return original(self, line_index)

    monkeypatch.setattr(TextArea, "get_line", _recording_get_line)

    area = TranscriptArea()
    area.load_transcript(["• hello"], line_styles=[[(0, 1, RichStyle(bold=True))]])

    first = area.get_line(0)
    second = area.get_line(0)

    assert calls == [0]
    assert first is not second
    assert first.spans == second.spans


class _SelectionArea:
    def __init__(
        self,
        *,
        anchor: tuple[int, int],
        selection_end: tuple[int, int],
        target: tuple[int, int],
    ) -> None:
        self._is_drag_selecting = True
        self._drag_anchor_location = anchor
        self._target = target
        self._selection = Selection(anchor, selection_end)
        self.selection_updates: list[Selection] = []

    @property
    def selection(self) -> Selection:
        return self._selection

    @selection.setter
    def selection(self, value: Selection) -> None:
        self.selection_updates.append(value)
        self._selection = value

    def get_target_document_location(self, _event) -> tuple[int, int]:
        return self._target


class _MouseEvent:
    def stop(self) -> None:
        return None

    def prevent_default(self) -> None:
        return None


def test_transcript_drag_selection_skips_noop_mouse_move() -> None:
    area = _SelectionArea(anchor=(2, 4), selection_end=(5, 9), target=(5, 9))

    transcript_selection_runtime.on_mouse_move(area, _MouseEvent())

    assert area.selection_updates == []


def test_transcript_drag_selection_updates_when_target_changes() -> None:
    area = _SelectionArea(anchor=(2, 4), selection_end=(5, 9), target=(6, 1))

    transcript_selection_runtime.on_mouse_move(area, _MouseEvent())

    assert len(area.selection_updates) == 1
    assert area.selection.end == (6, 1)
