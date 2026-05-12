from __future__ import annotations

import json
import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def _write_python_file(path: Path, *, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * max(0, int(lines)), encoding="utf-8")


def test_quality_size_guard_main_passes_when_hard_hit_is_allowlisted(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    root = tmp_path / "pkg"
    target = root / "large_module.py"
    _write_python_file(target, lines=8)

    baseline = tmp_path / "size_guard_baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "allow_over_hard": {
                    target.as_posix(): 8,
                }
            }
        ),
        encoding="utf-8",
    )

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

    assert rc == 0
    assert "[size-guard] soft_violations=1 hard_violations=1" in output
    assert "[size-guard] hard gate failed:" not in output
    assert "[size-guard] pass" in output
