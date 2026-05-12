from __future__ import annotations

import json
import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def test_quality_size_guard_main_passes_when_root_has_no_python_files(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    root = tmp_path / "empty_pkg"
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("no python files here\n", encoding="utf-8")
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
    assert "[size-guard] scanned=0 soft_limit=3 hard_limit=5" in output
    assert "[size-guard] soft_violations=0 hard_violations=0" in output
    assert "[size-guard] pass" in output
