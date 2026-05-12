from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_allows_explicit_root_override(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--root",
            "custom/root/path",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.root == "custom/root/path"
