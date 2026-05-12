from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_root_override_keeps_default_baseline_value_exactly(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--root",
            "./tmp/../custom_root",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.root == "./tmp/../custom_root"
    assert args.baseline == "cli/scripts/size_guard_baseline.json"

