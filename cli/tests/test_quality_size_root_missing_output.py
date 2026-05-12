from __future__ import annotations

import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def test_quality_size_guard_main_root_missing_outputs_message_and_returns_two(
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
        ],
    )

    rc = quality_size_guard.main()
    output = capsys.readouterr().out

    assert rc == 2
    assert output.strip() == f"[size-guard] root not found: {missing_root}"
