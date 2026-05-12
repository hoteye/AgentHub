from __future__ import annotations

import re
import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def _write_python_file(path: Path, *, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * max(0, int(lines)), encoding="utf-8")


def test_quality_size_guard_soft_violations_output_is_capped_to_top_20(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    root = tmp_path / "pkg"
    baseline = tmp_path / "size_guard_baseline.json"
    baseline.write_text('{"allow_over_hard": {}}', encoding="utf-8")

    for idx in range(1, 26):
        _write_python_file(root / f"module_{idx:02d}.py", lines=idx + 1)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--root",
            str(root),
            "--soft",
            "1",
            "--hard",
            "1000",
            "--baseline",
            str(baseline),
        ],
    )

    rc = quality_size_guard.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "[size-guard] soft_violations=25 hard_violations=0" in out
    assert "[size-guard] soft violations (top 20):" in out

    violation_lines = re.findall(r"^\s+\d+\s+.*\.py$", out, flags=re.MULTILINE)
    assert len(violation_lines) == 20

    assert str((root / "module_25.py").as_posix()) in out
    assert str((root / "module_06.py").as_posix()) in out
    assert str((root / "module_05.py").as_posix()) not in out
    assert str((root / "module_01.py").as_posix()) not in out
