from __future__ import annotations

import json
import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def _write_python_file(path: Path, *, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * max(0, int(lines)), encoding="utf-8")


def test_quality_size_guard_main_reports_all_hard_failures_and_returns_one(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    root = tmp_path / "pkg"
    file_a = root / "too_big_a.py"
    file_b = root / "too_big_b.py"
    _write_python_file(file_a, lines=7)
    _write_python_file(file_b, lines=8)

    baseline = tmp_path / "size_guard_baseline.json"
    baseline.write_text(json.dumps({"allow_over_hard": {}}), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--root",
            str(root),
            "--soft",
            "3",
            "--hard",
            "5",
            "--baseline",
            str(baseline),
        ],
    )

    rc = quality_size_guard.main()
    output = capsys.readouterr().out

    assert rc == 1
    assert "[size-guard] hard gate failed:" in output
    assert f"  - {file_a.as_posix()} has 7 lines (> 5) and is not in baseline allowlist" in output
    assert f"  - {file_b.as_posix()} has 8 lines (> 5) and is not in baseline allowlist" in output
