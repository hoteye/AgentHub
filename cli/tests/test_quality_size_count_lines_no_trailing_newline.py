from __future__ import annotations

from pathlib import Path

from cli.scripts import quality_size_guard


def test_count_lines_counts_last_line_without_trailing_newline(tmp_path: Path) -> None:
    target = tmp_path / "no_trailing_newline.py"
    target.write_text("alpha = 1\nbeta = 2\ngamma = 3", encoding="utf-8")

    lines = quality_size_guard.count_lines(target)

    assert lines == 3
