from __future__ import annotations

import json
import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def _write_python_file(path: Path, *, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * max(0, int(lines)), encoding="utf-8")


def test_quality_size_guard_soft_violation_listing_is_sorted_descending(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    root = tmp_path / "pkg"
    _write_python_file(root / "a.py", lines=7)
    _write_python_file(root / "b.py", lines=7)
    _write_python_file(root / "c.py", lines=6)

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
            "5",
            "--hard",
            "20",
            "--baseline",
            str(baseline),
        ],
    )

    rc = quality_size_guard.main()
    output = capsys.readouterr().out

    assert rc == 0
    assert "[size-guard] soft_violations=3 hard_violations=0" in output
    assert "[size-guard] soft violations (top 20):" in output

    lines = [line.rstrip() for line in output.splitlines()]
    marker = "[size-guard] soft violations (top 20):"
    start = lines.index(marker) + 1
    listed = [line.strip() for line in lines[start : start + 3]]

    # sorted(soft_hits, reverse=True): lines desc, then path desc for ties.
    assert listed[0].endswith(f"{(root / 'b.py').as_posix()}")
    assert listed[0].startswith("7")
    assert listed[1].endswith(f"{(root / 'a.py').as_posix()}")
    assert listed[1].startswith("7")
    assert listed[2].endswith(f"{(root / 'c.py').as_posix()}")
    assert listed[2].startswith("6")
