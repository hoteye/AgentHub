from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_soft_override_keeps_int_type_and_value(monkeypatch) -> None:
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

    assert isinstance(args.soft, int)
    assert not isinstance(args.soft, str)
    assert args.soft == 123
