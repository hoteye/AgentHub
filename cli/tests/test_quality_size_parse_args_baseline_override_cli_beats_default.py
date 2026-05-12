from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_baseline_override_beats_default(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--baseline",
            "tmp/custom_baseline.json",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.baseline == "tmp/custom_baseline.json"
    assert args.baseline != "cli/scripts/size_guard_baseline.json"
