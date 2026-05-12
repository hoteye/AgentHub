from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_root_override_beats_default_root(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--root",
            "cli/custom_root",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.root == "cli/custom_root"
    assert args.root != "cli/agent_cli"
