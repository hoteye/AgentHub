from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_baseline_override_keeps_exact_cli_value(monkeypatch) -> None:
    # Contract: argparse should preserve the exact CLI string, not normalize paths.
    cli_value = "./tmp/../tmp/custom_baseline.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quality_size_guard.py",
            "--baseline",
            cli_value,
        ],
    )

    args = quality_size_guard.parse_args()

    assert args.baseline == cli_value
