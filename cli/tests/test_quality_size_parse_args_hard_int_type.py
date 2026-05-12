from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_parses_hard_as_int(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--hard",
            "512",
        ],
    )

    args = quality_size_guard.parse_args()

    assert isinstance(args.hard, int)
    assert args.hard == 512
