from __future__ import annotations

import sys

from cli.scripts import quality_size_guard


def test_quality_size_parse_args_defaults_keep_value_and_type_contract(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["quality_size_guard.py"])

    args = quality_size_guard.parse_args()

    assert args.soft == 350
    assert isinstance(args.soft, int)
    assert args.hard == 500
    assert isinstance(args.hard, int)
    assert args.root == "cli/agent_cli"
    assert isinstance(args.root, str)
    assert args.baseline == "cli/scripts/size_guard_baseline.json"
    assert isinstance(args.baseline, str)
