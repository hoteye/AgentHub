from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_baseline_override_keeps_root_default(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--baseline",
            "tmp/custom_baseline.json",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.baseline == "tmp/custom_baseline.json"
    assert args.root == "cli/agent_cli"


def test_quality_size_parse_args_baseline_override_keeps_cli_root(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--baseline",
            "tmp/custom_baseline.json",
            "--root",
            "cli/custom_root",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.baseline == "tmp/custom_baseline.json"
    assert args.root == "cli/custom_root"
