from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_soft_override(monkeypatch) -> None:
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

    assert args.root == "cli/agent_cli"
    assert args.soft == 123
    assert args.hard == 500
    assert args.baseline == "cli/scripts/size_guard_baseline.json"
