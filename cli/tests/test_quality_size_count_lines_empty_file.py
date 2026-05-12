from __future__ import annotations

from pathlib import Path

from cli.scripts import quality_size_guard


def test_count_lines_returns_zero_for_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "empty.py"
    target.write_text("", encoding="utf-8")

    lines = quality_size_guard.count_lines(target)

    assert lines == 0
