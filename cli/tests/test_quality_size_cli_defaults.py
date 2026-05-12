from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_guard_parse_args_defaults_contract(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["quality_size_guard.py"])

    args = quality_size_guard.parse_args()

    assert args.root == "cli/agent_cli"
    assert args.soft == 350
    assert args.hard == 500
    assert args.baseline == "cli/scripts/size_guard_baseline.json"


def test_quality_size_guard_parse_args_allows_explicit_override(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--root",
            "pkg",
            "--soft",
            "120",
            "--hard",
            "240",
            "--baseline",
            "tmp/baseline.json",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.root == "pkg"
    assert args.soft == 120
    assert args.hard == 240
    assert args.baseline == "tmp/baseline.json"
