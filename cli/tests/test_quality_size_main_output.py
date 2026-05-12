from __future__ import annotations

import json
import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def _write_python_file(path: Path, *, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * max(0, int(lines)), encoding="utf-8")


def test_quality_size_guard_main_pass_outputs_summary_and_returns_zero(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    root = tmp_path / "pkg"
    _write_python_file(root / "ok.py", lines=2)
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

    assert rc == 0
    assert "[size-guard] scanned=1 soft_limit=3 hard_limit=5" in output
    assert "[size-guard] soft_violations=0 hard_violations=0" in output
    assert "[size-guard] pass" in output


def test_quality_size_guard_main_fail_outputs_summary_and_returns_one(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    root = tmp_path / "pkg"
    _write_python_file(root / "too_big.py", lines=6)
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
    assert "[size-guard] scanned=1 soft_limit=3 hard_limit=5" in output
    assert "[size-guard] soft_violations=1 hard_violations=1" in output
    assert "[size-guard] soft violations (top 20):" in output
    assert "[size-guard] hard gate failed:" in output
    assert "is not in baseline allowlist" in output
    assert "[size-guard] hint: split file or tighten baseline intentionally." in output
