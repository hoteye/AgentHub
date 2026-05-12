from __future__ import annotations

import json
import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def _write_python_file(path: Path, *, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * max(0, int(lines)), encoding="utf-8")


def test_quality_size_guard_main_pass_path_does_not_print_hard_gate_failed_header(
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
    out = capsys.readouterr().out

    assert rc == 0
    assert "[size-guard] pass" in out
    assert "[size-guard] hard gate failed:" not in out
