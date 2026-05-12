from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_root_override_keeps_default_baseline_when_baseline_not_set(monkeypatch) -> None:
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
    assert args.baseline == "cli/scripts/size_guard_baseline.json"


def test_root_override_does_not_override_explicit_baseline(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--root",
            "custom/root/path",
            "--baseline",
            "tmp/custom_baseline.json",
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.root == "custom/root/path"
    assert args.baseline == "tmp/custom_baseline.json"
