from __future__ import annotations

import json
import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def _write_python_file(path: Path, *, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * max(0, int(lines)), encoding="utf-8")


def test_quality_size_guard_returns_2_when_root_missing(monkeypatch, capsys, tmp_path: Path) -> None:
    missing_root = tmp_path / "missing_root"
    monkeypatch.setattr(
        sys,
        "argv",
        ["quality_size_guard.py", "--root", str(missing_root)],
    )

    rc = quality_size_guard.main()
    captured = capsys.readouterr().out

    assert rc == 2
    assert f"[size-guard] root not found: {missing_root}" in captured


def test_quality_size_guard_fails_hard_violation_when_not_in_baseline_allowlist(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    root = tmp_path / "pkg"
    target = root / "module.py"
    _write_python_file(target, lines=6)
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
    captured = capsys.readouterr().out

    assert rc == 1
    assert "[size-guard] soft_violations=1 hard_violations=1" in captured
    assert "[size-guard] hard gate failed:" in captured
    assert "is not in baseline allowlist" in captured
    assert "[size-guard] hint: split file or tighten baseline intentionally." in captured


def test_quality_size_guard_baseline_allowlist_cap_allows_and_then_blocks(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    root = tmp_path / "pkg"
    target = root / "module.py"
    _write_python_file(target, lines=6)
    baseline = tmp_path / "size_guard_baseline.json"
    key = target.as_posix()

    baseline.write_text(json.dumps({"allow_over_hard": {key: 6}}), encoding="utf-8")
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
    rc_allow = quality_size_guard.main()
    captured_allow = capsys.readouterr().out
    assert rc_allow == 0
    assert "[size-guard] soft_violations=1 hard_violations=1" in captured_allow
    assert "[size-guard] pass" in captured_allow

    baseline.write_text(json.dumps({"allow_over_hard": {key: 5}}), encoding="utf-8")
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
    rc_block = quality_size_guard.main()
    captured_block = capsys.readouterr().out
    assert rc_block == 1
    assert "exceeds baseline cap 5 (hard 5)" in captured_block
