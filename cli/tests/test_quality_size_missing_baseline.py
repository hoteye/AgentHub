from __future__ import annotations

import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def test_quality_size_guard_fails_when_baseline_missing_and_hard_hit_exists(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    root = tmp_path / "pkg"
    target = root / "too_large.py"
    root.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1\n" * 6, encoding="utf-8")
    missing_baseline = tmp_path / "missing_baseline.json"

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
            str(missing_baseline),
        ],
    )

    rc = quality_size_guard.main()
    captured = capsys.readouterr().out

    assert rc == 1
    assert "[size-guard] soft_violations=1 hard_violations=1" in captured
    assert "[size-guard] hard gate failed:" in captured
    assert "is not in baseline allowlist" in captured
