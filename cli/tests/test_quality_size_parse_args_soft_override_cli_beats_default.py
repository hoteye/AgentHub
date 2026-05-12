from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_soft_override_beats_default(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--soft",
            "123",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.soft == 123
    assert args.soft != 350
