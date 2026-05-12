from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_root_override_keeps_exact_cli_value(monkeypatch) -> None:
    root_value = "./cli//custom_root/../target_root"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--root",
            root_value,
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.root == root_value
