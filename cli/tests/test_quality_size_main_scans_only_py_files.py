from __future__ import annotations

import json
import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def test_quality_size_guard_main_scans_only_python_files_in_root(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    root = tmp_path / "pkg"
    root.mkdir(parents=True, exist_ok=True)

    (root / "module_a.py").write_text("a = 1\n", encoding="utf-8")
    (root / "module_b.py").write_text("b = 2\nb = 3\n", encoding="utf-8")
    (root / "README.md").write_text("notes\n", encoding="utf-8")
    (root / "config.yaml").write_text("k: v\n", encoding="utf-8")
    (root / "data.txt").write_text("payload\n", encoding="utf-8")

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
            "10",
            "--hard",
            "20",
            "--baseline",
            str(baseline),
        ],
    )

    rc = quality_size_guard.main()
    output = capsys.readouterr().out

    assert rc == 0
    assert "[size-guard] scanned=2 soft_limit=10 hard_limit=20" in output
    assert "[size-guard] soft_violations=0 hard_violations=0" in output
    assert "[size-guard] pass" in output
