from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_allows_explicit_hard_override(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--hard",
            "640",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.hard == 640
