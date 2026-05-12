from __future__ import annotations

from pathlib import Path

from cli.scripts import quality_size_guard


def test_count_lines_counts_crlf_lines_as_normal_lines(tmp_path: Path) -> None:
    target = tmp_path / "windows_style.py"
    target.write_bytes(b"alpha = 1\r\nbeta = 2\r\ngamma = 3\r\n")

    lines = quality_size_guard.count_lines(target)

    assert lines == 3
