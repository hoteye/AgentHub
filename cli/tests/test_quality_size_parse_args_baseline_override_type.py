from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_baseline_override_preserves_str_type(monkeypatch) -> None:
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

    assert isinstance(args.baseline, str)
    assert args.baseline == "tmp/custom_baseline.json"
