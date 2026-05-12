from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_hard_override_keeps_int_type(monkeypatch) -> None:
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

    assert isinstance(args.hard, int)
    assert not isinstance(args.hard, str)
    assert args.hard == 777
