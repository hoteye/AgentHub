from __future__ import annotations

import sys
from pathlib import Path

from cli.scripts import quality_size_guard


def test_main_wraps_baseline_arg_with_path_for_load_baseline(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir(parents=True, exist_ok=True)
    baseline_arg = tmp_path / "custom-baseline.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--root",
            str(root),
            "--baseline",
            str(baseline_arg),
        ],
    )

    observed: list[Path] = []

    def _fake_load_baseline(path: Path) -> dict[str, int]:
        observed.append(path)
        return {}

    monkeypatch.setattr(quality_size_guard, "load_baseline", _fake_load_baseline)

    rc = quality_size_guard.main()

    assert rc == 0
    assert observed == [Path(str(baseline_arg))]
    assert isinstance(observed[0], Path)
