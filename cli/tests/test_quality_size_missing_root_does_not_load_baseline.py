from __future__ import annotations

import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def test_main_returns_two_and_skips_load_baseline_when_root_missing(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    missing_root = tmp_path / "missing_root"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--root",
            str(missing_root),
            "--baseline",
            str(tmp_path / "baseline.json"),
        ],
    )

    def _should_not_be_called(_path: Path):
        raise AssertionError("load_baseline should not be called when root is missing")

    monkeypatch.setattr(quality_size_guard, "load_baseline", _should_not_be_called)

    rc = quality_size_guard.main()
    output = capsys.readouterr().out

    assert rc == 2
    assert output.strip() == f"[size-guard] root not found: {missing_root}"
