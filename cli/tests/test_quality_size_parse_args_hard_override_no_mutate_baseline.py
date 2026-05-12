from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_hard_override_does_not_mutate_baseline_default(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--hard",
            "777",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.hard == 777
    assert args.baseline == "cli/scripts/size_guard_baseline.json"
