from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_hard_override_keeps_default_root(monkeypatch) -> None:
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
    assert args.root == "cli/agent_cli"


def test_quality_size_parse_args_hard_override_does_not_mutate_explicit_root(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--hard",
            "640",
            "--root",
            "cli/custom_root",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.hard == 640
    assert args.root == "cli/custom_root"
